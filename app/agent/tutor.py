"""Tutor agent — a conversational study tutor with native OpenAI tool-calling.

The local endpoint speaks standard OpenAI function-calling (`tool_calls` on
the assistant message), so each turn runs a tool loop over `chat_with_tools`:
send messages + schemas → execute returned tool calls → append `role: "tool"`
results → repeat until a final text reply (max MAX_TOOL_ROUNDS).

Tool implementations live in tutor_tools.py and call the existing service
layer directly — tutor behavior never duplicates app logic.

Mutation rule (confirm-in-chat): mutating tools take `confirmed: bool = False`.
With confirmed=False they do NOTHING except return a plain-language proposal
the tutor shows the user. Only after the user says yes does the tutor re-call
with confirmed=True. Memory writes (`remember`), background learning writes
(`record_understanding`), read-only questions (`ask_clarify`), and
`ui_command` are exempt.

Per-turn context (Learner Snapshot) is prepended every turn: weakest topics,
SM-2 items due, recent quiz average, upcoming deadlines — so the tutor
diagnoses before answering without extra tool calls.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from sqlalchemy import func, select

from .. import ai as _ai_module
from .. import models
from ..ai import chat_stream  # noqa: F401 - graph resolves this patchable stream entry
from . import cards as card_registry
from .graph import open_graph_turn, run_graph_turn, stream_agent_loop
from .prompt import QUIZ_DEBRIEF_PROMPT, TUTOR_PROMPT
from .tutor_tools import (  # noqa: F401 - graph context pin
    current_conversation,
    openai_tools,
    run_tool,
)


async def chat_with_tools(messages, tools=None, temperature=0.4, tool_choice="auto", thread_id=None):
    """Re-exported LLM entry so tests can patch tutor.chat_with_tools."""
    return await _ai_module.chat_with_tools(
        messages, tools=tools, temperature=temperature,
        tool_choice=tool_choice, thread_id=thread_id,
    )

MAX_TOOL_ROUNDS = 8
PREVIEW_LEN = 300


def _library_line(db, user_id: int) -> str:
    """Static library structure for the SYSTEM prompt (sent once per
    conversation): courses with modules and topics, ids only — no scores,
    no passage counts, nothing dynamic. The model refetches via
    get_course_tree when the library changes or it needs detail."""
    from .tutor_tools import course_tree as _course_tree

    courses = db.scalars(
        select(models.Course).where(models.Course.user_id == user_id)
    ).all()
    if not courses:
        return "LIBRARY STRUCTURE: (no courses yet)"
    parts = []
    for c in courses:
        tree = _course_tree(db, user_id, c.id) or {}
        mods = []
        for m in tree.get("modules", []):
            topics = ", ".join(f"{t['name']} (t{t['id']})" for t in m["topics"])
            mods.append(f"{m['name']} [m{m['id']}]: {topics or '(no topics)'}")
        parts.append(f"{c.name} (c{c.id}): " + (" | ".join(mods) or "(no modules)"))
    line = "LIBRARY STRUCTURE (Course > Module > Topic; quiz/passage/review/timer tools take topic_id): " + " ;; ".join(parts)
    if len(line) > 1500:
        short = "; ".join(f"{c.name} (c{c.id})" for c in courses)
        line = f"LIBRARY STRUCTURE (condensed — call get_course_tree per course for topics): {short}"
    return line


def build_snapshot(db, user_id: int) -> str:
    """Minimal learner-state brief injected every turn.

    Deliberately slim: weakest topics and due reviews are fetchable via tools
    (get_proficiency / get_due_reviews), so they don't ride along unasked.
    Only what the tutor can't cheaply fetch stays here.
    """
    avg = db.scalar(
        select(func.avg(models.Attempt.score)).where(
            models.Attempt.user_id == user_id,
            models.Attempt.status == "graded",
        )
    )
    upcoming = db.scalars(
        select(models.Deadline)
        .where(models.Deadline.user_id == user_id)
        .order_by(models.Deadline.due_date)
        .limit(3)
    ).all()
    mems = db.scalars(
        select(models.TutorMemory).where(models.TutorMemory.user_id == user_id)
    ).all()
    return (
        f"Recent quiz avg: {(avg or 0):.2f} | "
        f"Deadlines: {', '.join(f'{d.title} ({d.due_date})' for d in upcoming) or 'none'} | "
        f"Notes: {'; '.join(f'{m.key}: {m.value}' for m in mems) or 'none'}"
    )


def _thread_id(user_id: int, conversation_id: int) -> str:
    """Stable server-side thread per tutor conversation.

    The DeepSeek proxy keys its web conversation off this id and keeps
    history server-side, so each turn sends only the delta (new user/tool
    messages) instead of spawning a fresh conversation per turn.
    """
    return f"tutor_u{user_id}_c{conversation_id}"


def _stable_system(custom: str, library: str = "") -> str:
    """System prompt that is IDENTICAL every turn of a conversation.

    `custom` is the already-rendered persona block from prompt.persona_block
    (kept as a param so call sites don't change); the canonical assembly
    lives in prompt.build_system_prompt — the Settings preview renders the
    same function, so what you see there is what the model gets.

    Per-turn state (learner snapshot, UI state) rides on the latest user
    message instead — the proxy only forwards the system block on the
    first exchange and appends deltas after that. The static library
    structure rides here too (one-time cost); dynamic scores/counts stay
    in the snapshot or behind get_course_tree.
    """
    base = f"{TUTOR_PROMPT}{custom}"
    return f"{base}\n\n{library}" if library else base


def _persona_for(pref) -> str:
    """Thin adapter: Preference row -> prompt.persona_block (single source)."""
    from .prompt import persona_block as _pb

    if pref is None:
        return _pb(None, None, None)
    return _pb(
        getattr(pref, "tutor_style", None),
        getattr(pref, "tutor_verbosity", None),
        getattr(pref, "tutor_instructions", None),
    )


def _todo_line(db, conversation_id: int) -> str:
    """Per-turn plan state for the prompt (this conversation only).

    The model demonstrably acts on per-turn context (snapshot, UI state) and
    ignores buried system-prompt lines — so the active plan and the
    create/maintain instruction ride the user message every turn, keeping
    update_todo calls and the side-panel graph in sync with the teaching.
    """
    last = db.scalar(
        select(models.Card)
        .where(
            models.Card.conversation_id == conversation_id,
            models.Card.kind == "todo",
        )
        .order_by(models.Card.id.desc())
    )
    if last is None:
        return (
            "\n\nPLAN: none active. If this turn starts multi-step work "
            "(2+ steps), call update_todo FIRST to open one — never claim a "
            "plan is tracked without the update_todo tool result in this turn."
        )
    try:
        args = last.payload or {}
        todos = args.get("todos", [])
        total = args.get("total", len(todos))
        done = args.get("completed", sum(1 for t in todos if t.get("status") == "completed"))
        current = args.get("current_active") or args.get("current") or "?"
        shares = ", ".join(
            f"{t.get('content', '?')[:40]} ({round((t.get('weight') or 0) * 100)}%, {t.get('status')})"
            for t in todos
        )
    except (AttributeError, IndexError, TypeError):
        return ""
    if done >= total:
        return f"\n\nPLAN: complete ({done}/{total}). Open a new one with update_todo when fresh multi-step work starts."
    return (
        f"\n\nPLAN: {done}/{total} done, current step: '{current}'. "
        f"Shares: {shares}. "
        "When the current step completes, score it with record_understanding "
        "using coverage = its share (weight × demonstrated is the fair topic "
        "credit), then re-call update_todo with the FULL updated list — "
        "the side panel graphs exactly what you last wrote."
    )


def _open_turn(db, user_id: int, conversation_id: int | None, message: str,
               ui_context: dict | None = None, images: list[str] | None = None):
    """Get/create conversation, persist the user message, build the prompt.

    Returns (conversation_id, messages, thread_id) where messages are
    proper OpenAI roles: one stable system + the recent history as
    alternating user/assistant turns, ending with the new user turn that
    carries the fresh snapshot/UI state. History itself is never rewritten
    — new turns only append.
    """
    if conversation_id is None:
        conv = models.Conversation(user_id=user_id, title=message[:60] or "Tutor chat")
        pin = (ui_context or {}).get("module_id")
        if pin is not None:
            from .tutor_tools import _resolve_pin

            module = _resolve_pin(db, user_id, pin)
            if not isinstance(module, dict) and module is not None:
                conv.module_id = module.id
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conversation_id = conv.id
    else:
        conv = db.get(models.Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise ValueError("Conversation not found")

    # Keep the image outside the transcript: history rendering can show it,
    # while subsequent model turns keep the text-only history compact.
    db.add(models.ChatMessage(
        conversation_id=conversation_id,
        role="user",
        content=message,
        images=(images or [])[:1] or None,
    ))
    db.commit()

    _stamp_clarify_answered(db, conversation_id, message)

    history = db.scalars(
        select(models.ChatMessage)
        .where(models.ChatMessage.conversation_id == conversation_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(30)
    ).all()
    # Oldest-first, user/assistant only (quiz/clarify cards render inline).
    ordered = list(reversed(history))
    # Exclude the just-persisted message from the history prefix; it is
    # re-attached below with the fresh snapshot attached.
    ordered = [m for m in ordered if m.role in ("user", "assistant")]
    prior = ordered[:-1]
    messages: list[dict] = []
    snapshot = build_snapshot(db, user_id)
    pref = db.get(models.Preference, user_id)
    custom = _persona_for(pref)
    library = _library_line(db, user_id)
    messages.append({"role": "system", "content": _stable_system(custom, library)})
    for m in prior[-20:]:
        messages.append({
            "role": m.role,
            "content": m.content,
        })
    context_line = f"LEARNER SNAPSHOT: {snapshot}{_todo_line(db, conversation_id)}"
    # Stored pin is the module truth (permanent until set_context moves it).
    pin_id = getattr(conv, "module_id", None)
    if pin_id is not None:
        pin_mod = db.get(models.Module, pin_id)
        context_line += f"\nPINNED MODULE: {pin_mod.name if pin_mod else f'#{pin_id}'} (law — never search outside it unasked)"
    else:
        context_line += "\nPINNED MODULE: none (unpinned — resolve per question, state the module)"
    user_text = f"{context_line}\n\n{message}"
    user_content: str | list[dict] = user_text
    if images:
        # OpenAI multipart: text first, then the turn's image. The proxy
        # forwards the first image per turn; history stays text-only.
        user_content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": images[0]}},
        ]
    messages.append({
        "role": "user",
        "content": user_content,
    })
    return conversation_id, messages, _thread_id(user_id, conversation_id)


def _stamp_clarify_answered(db, conversation_id: int, message: str) -> None:
    """Mark the most recent still-open clarify card answered by this message.

    The card keeps its question/options (history is append-only) and gains
    completed=True + the learner's answer, so reloads render it read-only.
    (JSON columns need full reassignment for change tracking.)
    """
    open_cards = db.scalars(
        select(models.Card)
        .where(
            models.Card.conversation_id == conversation_id,
            models.Card.kind == "clarify",
        )
        .order_by(models.Card.id.desc())
    ).all()
    for card in open_cards:
        args = dict(card.payload or {})
        if args.get("completed"):
            continue
        card.payload = {**args, "completed": True, "answer": message[:500]}
        db.commit()
        break


def _preview(result) -> str:
    try:
        text = json.dumps(result)
    except (TypeError, ValueError):
        text = str(result)
    return text[:PREVIEW_LEN]


def _close_turn(db, conversation_id: int, reply: str, tool_calls: list[dict]) -> int:
    """Persist the assistant reply; returns its id (card display anchor)."""
    msg = models.ChatMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=reply,
        tool_calls=tool_calls or None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg.id


def _finalize_turn(
    db, conversation_id: int, reply: str, tool_calls: list[dict],
    ui_actions: list[dict], cards: dict[str, dict],
) -> dict:
    """Persist the turn (assistant reply + optional inline cards) and build
    the turn dict shared by the sync and streaming paths.

    cards maps kind -> raw tool payload; first-wins/last-wins already applied
    by the loops. Turn keys (quiz/clarify/review/timer/todo/video) keep their
    exact legacy shapes — see cards.slim.
    """
    anchor_id = _close_turn(db, conversation_id, reply, tool_calls)
    out: dict = {
        "conversation_id": conversation_id,
        "reply": reply,
        "tool_calls": tool_calls,
        "ui_actions": ui_actions,
        "quiz": None,
        "clarify": None,
        "review": None,
        "timer": None,
        "todo": None,
        "video": None,
    }
    for kind, raw in cards.items():
        payload = card_registry.slim(kind, raw)
        if kind == "timer":
            out["timer"] = payload
            continue
        if kind == "quiz":
            # The inline card replaces the old open_quiz navigation this turn.
            out["ui_actions"] = [a for a in ui_actions if a.get("action") != "open_quiz"]
        card = card_registry.persist_card(
            db, conversation_id, kind, payload, message_id=anchor_id
        )
        out[kind] = {"message_id": card.id, **payload}
    return out


def run_tutor_turn(db, user_id: int, conversation_id: int | None, message: str,
                   ui_context: dict | None = None, images: list[str] | None = None) -> dict:
    """One LangGraph-backed chat turn; persist and return the API payload."""
    return run_graph_turn(db, user_id, conversation_id, message, ui_context, images)


def _parse_call(call: dict) -> tuple[str, dict]:
    name = call["function"]["name"]
    try:
        args = json.loads(call["function"].get("arguments") or "{}")
    except json.JSONDecodeError:
        args = {}
    return name, args


def _execute_call(db, user_id: int, name: str, args: dict) -> tuple[dict, dict | None]:
    """Run one tool (sync loop). Coroutine results are driven with asyncio.run
    — safe here because the sync endpoint runs with no event loop."""
    import inspect

    try:
        result = run_tool(db, user_id, name, args)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
    except Exception as e:  # noqa: BLE001 — tool errors go back to the model
        result = {"error": f"{type(e).__name__}: {e}"}
    ui_action = None
    if name == "ui_command" and isinstance(result, dict) and result.get("queued"):
        ui_action = {"action": args.get("action"), "params": args.get("params", {})}
    return result, ui_action


async def _aexecute_call(db, user_id: int, name: str, args: dict) -> tuple[dict, dict | None]:
    """Run one tool (streaming loop). Awaits coroutine results in place —
    this is the fix for 'event loop already running': nothing blocks."""
    import inspect

    try:
        result = run_tool(db, user_id, name, args)
        if inspect.isawaitable(result):
            result = await result
    except Exception as e:  # noqa: BLE001 — tool errors go back to the model
        result = {"error": f"{type(e).__name__}: {e}"}
    ui_action = None
    if name == "ui_command" and isinstance(result, dict) and result.get("queued"):
        ui_action = {"action": args.get("action"), "params": args.get("params", {})}
    return result, ui_action


def _dedupe_key(name: str, args: dict) -> str:
    try:
        return f"{name}:{json.dumps(args, sort_keys=True)}"
    except (TypeError, ValueError):
        return f"{name}:{args}"


def openai_tools_shim() -> list[dict]:
    """Late-bound accessor so graph.py avoids a module-level import cycle."""
    return openai_tools()


def _run_tool_loop(db, user_id: int, conversation_id: int, messages: list[dict],
                   thread_id: str | None = None) -> dict:
    # Canonical loop lives in graph.run_agent_loop (LangGraph model<->tools).
    from .graph import run_agent_loop

    return run_agent_loop(
        db, user_id, conversation_id, messages, thread_id, openai_tools(),
    )


def _run_tool_loop_inner(db, user_id: int, conversation_id: int, messages: list[dict],
                          thread_id: str | None, tools: list[dict]) -> dict:
    # Kept for tests/callers: same canonical loop with explicit tools.
    from .graph import run_agent_loop

    return run_agent_loop(
        db, user_id, conversation_id, messages, thread_id, tools,
    )


def run_quiz_debrief(db, user_id: int, conversation_id: int, assessment_id: int) -> dict:
    """Finish an in-chat quiz: build a HIDDEN graded summary (never persisted
    as a user message, so grades stay out of the transcript) and run a tutor
    turn that returns ONLY the recommendation. Only the assistant reply is
    persisted — via _run_tool_loop → _finalize_turn."""
    conv = db.get(models.Conversation, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise ValueError("Conversation not found")
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None or assessment.user_id != user_id:
        raise ValueError("Assessment not found")

    questions = db.scalars(
        select(models.Question)
        .join(models.AssessmentQuestion,
              models.AssessmentQuestion.question_id == models.Question.id)
        .where(models.AssessmentQuestion.assessment_id == assessment_id)
        .order_by(models.AssessmentQuestion.order_index)
    ).all()
    attempts = {
        a.question_id: a
        for a in db.scalars(
            select(models.Attempt).where(
                models.Attempt.assessment_id == assessment_id,
                models.Attempt.user_id == user_id,
            )
        ).all()
    }
    lines = []
    for i, q in enumerate(questions, 1):
        topic = db.get(models.Topic, q.topic_id)
        a = attempts.get(q.id)
        if a is None or (a.score is None and not (a.user_answer or "").strip()):
            lines.append(
                f"{i}. [{topic.name if topic else q.topic_id}] {q.text[:200]}"
                " — NOT ATTEMPTED"
            )
            continue
        lines.append(
            f"{i}. [{topic.name if topic else q.topic_id}] {q.text[:200]}\n"
            f"   Their answer: {(a.user_answer or '').strip()[:400]}\n"
            f"   Score: {a.score:.2f} | Matched: {', '.join(a.matched_key_points or [])[:200]}\n"
            f"   Missed: {', '.join(a.missed_key_points or [])[:200]}\n"
            f"   Grader note: {(a.feedback or '')[:300]}"
        )
    summary = "\n".join(lines) or "(no questions)"

    assessment.status = "completed"
    assessment.completed_at = datetime.now()
    # Stamp the inline quiz card completed so reloads render a read-only
    # state (no typing UI) — review lives in the Quiz tab, not the chat.
    # (JSON columns need full reassignment for change tracking.)
    for card in db.scalars(
        select(models.Card).where(
            models.Card.conversation_id == conversation_id,
            models.Card.kind == "quiz",
        )
    ).all():
        args = dict(card.payload or {})
        if args.get("assessment_id") == assessment_id:
            card.payload = {**args, "completed": True}
    db.commit()

    history = db.scalars(
        select(models.ChatMessage)
        .where(models.ChatMessage.conversation_id == conversation_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(30)
    ).all()
    prior = [m for m in reversed(history) if m.role in ("user", "assistant")]
    snapshot = build_snapshot(db, user_id)
    library = _library_line(db, user_id)
    thread_id = _thread_id(user_id, conversation_id)
    pref = db.get(models.Preference, user_id)
    # Same system as a normal turn — persona included — plus the debrief task.
    messages = [
        {"role": "system", "content": f"{_stable_system(_persona_for(pref), library)}\n\n{QUIZ_DEBRIEF_PROMPT}"},
    ]
    for m in prior[-20:]:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": (
        f"LEARNER SNAPSHOT: {snapshot}{_todo_line(db, conversation_id)}\n\n"
        "=== HIDDEN QUIZ RESULTS (the student cannot see this — "
        "never quote scores, feedback, or rubrics) ===\n"
        f"{summary}\n\nWrite your debrief recommendation now."
    )})
    return _run_tool_loop(db, user_id, conversation_id, messages, thread_id)


async def stream_tutor_turn(db, user_id: int, conversation_id: int | None, message: str,
                          ui_context: dict | None = None, images: list[str] | None = None):
    """Streaming twin of run_tutor_turn. Yields event dicts:
    {"type": "tool", "tool", "args", "result_preview"},
    {"type": "token", "text"}, then {"type": "done", ...} (same shape as
    run_tutor_turn's return). Persists both messages like the sync version.
    """
    conversation_id, messages, thread_id = open_graph_turn(
        db, user_id, conversation_id, message, ui_context, images
    )
    async for event in stream_agent_loop(
        db, user_id, conversation_id, messages, thread_id, openai_tools(),
    ):
        yield event
