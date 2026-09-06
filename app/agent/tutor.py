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
with confirmed=True. Memory writes (`remember`) and `ui_command` are exempt.

Per-turn context (Learner Snapshot) is prepended every turn: weakest topics,
SM-2 items due, recent quiz average, upcoming deadlines — so the tutor
diagnoses before answering without extra tool calls.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from sqlalchemy import func, select

from .. import models
from ..ai import chat_stream, chat_with_tools
from ..services import ReviewService
from .prompt import QUIZ_DEBRIEF_PROMPT, TUTOR_PROMPT
from .tutor_tools import openai_tools, run_tool

MAX_TOOL_ROUNDS = 8
PREVIEW_LEN = 300


def build_snapshot(db, user_id: int) -> str:
    """Short learner-state brief injected every turn (no tool calls needed)."""
    n_courses = len(
        db.scalars(select(models.Course).where(models.Course.user_id == user_id)).all()
    )
    n_topics = db.scalar(
        select(func.count(models.Topic.id))
        .join(models.Module, models.Topic.module_id == models.Module.id)
        .join(models.Course, models.Module.course_id == models.Course.id)
        .where(models.Course.user_id == user_id)
    )
    profs = db.scalars(
        select(models.Proficiency)
        .where(models.Proficiency.user_id == user_id)
        .order_by(models.Proficiency.score)
        .limit(3)
    ).all()
    weak = []
    for r in profs:
        topic = db.get(models.Topic, r.topic_id)
        weak.append(f"{topic.name if topic else r.topic_id} ({r.score:.2f})")

    due = ReviewService.due_queue(db, user_id, limit=5)
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
        f"Library: {n_courses} course(s), {n_topics} topic(s) total | "
        f"Weakest topics: {', '.join(weak) or '(no scores yet)'} | "
        f"Reviews due: {len(due)} ({', '.join(t.name for t in due[:3]) or 'none'}) | "
        f"Recent quiz avg: {(avg or 0):.2f} | "
        f"Deadlines: {', '.join(f'{d.title} ({d.due_date})' for d in upcoming) or 'none'} | "
        f"Notes: {'; '.join(f'{m.key}: {m.value}' for m in mems) or 'none'}"
    )


def _open_turn(db, user_id: int, conversation_id: int | None, message: str,
               ui_context: dict | None = None):
    """Get/create conversation, persist the user message, build the prompt."""
    if conversation_id is None:
        conv = models.Conversation(user_id=user_id, title=message[:60] or "Tutor chat")
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conversation_id = conv.id
    else:
        conv = db.get(models.Conversation, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise ValueError("Conversation not found")

    db.add(models.ChatMessage(conversation_id=conversation_id, role="user", content=message))
    db.commit()

    history = db.scalars(
        select(models.ChatMessage)
        .where(models.ChatMessage.conversation_id == conversation_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(20)
    ).all()
    transcript = "\n".join(
        f"{'Student' if m.role == 'user' else 'Tutor'}: {m.content}"
        for m in reversed(history)
        if m.role in ("user", "assistant")  # quiz cards render inline; not LLM text
    )
    snapshot = build_snapshot(db, user_id)
    pref = db.get(models.Preference, user_id)
    custom = (
        f"\n\nSTUDENT'S CUSTOM INSTRUCTIONS (highest priority, follow them):\n{pref.tutor_instructions.strip()}"
        if pref and pref.tutor_instructions and pref.tutor_instructions.strip()
        else ""
    )
    messages = [
        {"role": "system", "content": f"{TUTOR_PROMPT}{custom}\n\nLEARNER SNAPSHOT: {snapshot}{_ui_state_line(ui_context)}"},
        {"role": "user", "content": f"CONVERSATION SO FAR:\n{transcript}\n\nRespond to the last student message."},
    ]
    return conversation_id, messages


def _ui_state_line(ui_context: dict | None) -> str:
    """Render reported frontend state for the prompt (route, course, ...)."""
    if not ui_context:
        return ""
    route = ui_context.get("route", "?")
    course = ui_context.get("course_name") or (
        f"#{ui_context['course_id']}" if ui_context.get("course_id") else "none selected"
    )
    extra = ui_context.get("detail")
    line = f"\n\nUI STATE: screen={route} | course={course}"
    if extra:
        line += f" | {extra}"
    return line


def _preview(result) -> str:
    try:
        text = json.dumps(result)
    except (TypeError, ValueError):
        text = str(result)
    return text[:PREVIEW_LEN]


def _close_turn(db, conversation_id: int, reply: str, tool_calls: list[dict]) -> None:
    db.add(
        models.ChatMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=reply,
            tool_calls=tool_calls or None,
        )
    )
    db.commit()


def _capture_quiz(name: str, result) -> dict | None:
    """Pull the inline-quiz payload out of a generate_quiz tool result."""
    if name != "generate_quiz" or not isinstance(result, dict):
        return None
    if result.get("type") != "assessment" or not result.get("questions"):
        return None
    return {
        "assessment_id": result.get("assessment_id"),
        "questions": result.get("questions"),
    }


def _persist_quiz_message(db, conversation_id: int, quiz: dict) -> int:
    """Persist the inline quiz as a role='quiz' message (payload rides the
    existing tool_calls JSON column — no migration) and return its id."""
    msg = models.ChatMessage(
        conversation_id=conversation_id,
        role="quiz",
        content="",
        tool_calls=[{"tool": "quiz", "args": quiz}],
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg.id


def _finalize_turn(db, conversation_id: int, reply: str, tool_calls: list[dict],
                   ui_actions: list[dict], quiz: dict | None) -> dict:
    """Persist the turn (assistant reply + optional inline quiz card) and
    build the turn dict shared by the sync and streaming paths."""
    _close_turn(db, conversation_id, reply, tool_calls)
    out: dict = {
        "conversation_id": conversation_id,
        "reply": reply,
        "tool_calls": tool_calls,
        "ui_actions": ui_actions,
        "quiz": None,
    }
    if quiz:
        # The inline card replaces the old open_quiz navigation this turn.
        out["ui_actions"] = [a for a in ui_actions if a.get("action") != "open_quiz"]
        message_id = _persist_quiz_message(db, conversation_id, quiz)
        out["quiz"] = {"message_id": message_id, **quiz}
    return out


def run_tutor_turn(db, user_id: int, conversation_id: int | None, message: str,
                   ui_context: dict | None = None) -> dict:
    """One chat turn (non-streamed): run the tool loop, persist, return reply."""
    conversation_id, messages = _open_turn(db, user_id, conversation_id, message, ui_context)
    return _run_tool_loop(db, user_id, conversation_id, messages)


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


def _run_tool_loop(db, user_id: int, conversation_id: int, messages: list[dict]) -> dict:
    tools = openai_tools()
    tool_calls: list[dict] = []
    ui_actions: list[dict] = []
    quiz: dict | None = None
    seen: set[str] = set()  # exact-duplicate (tool, args) calls run once per turn
    reply = ""
    for _ in range(MAX_TOOL_ROUNDS):
        msg = asyncio.run(chat_with_tools(messages, tools=tools, temperature=0.4))
        calls = msg.get("tool_calls") or []
        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": calls or None,
            }
        )
        if not calls:
            reply = msg.get("content") or ""
            if not reply.strip() and not tool_calls:
                # Empty completion — nudge once rather than saving a blank turn.
                messages.append(
                    {"role": "user", "content": "Please respond with text, or a tool call if one fits."}
                )
                continue
            break
        for call in calls:
            name, args = _parse_call(call)
            key = _dedupe_key(name, args)
            if key in seen:
                # Native call + proxy-translated duplicate of the same action:
                # answer from cache instead of executing twice.
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": json.dumps({"duplicate": True, "cached": True}),
                    }
                )
                continue
            seen.add(key)
            result, ui_action = _execute_call(db, user_id, name, args)
            tool_calls.append({"tool": name, "args": args, "result_preview": _preview(result)})
            if quiz is None:
                quiz = _capture_quiz(name, result)
            if ui_action is not None:
                ui_actions.append(ui_action)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result)[:4000],
                }
            )
    else:
        reply = reply or "Let me know how you'd like to proceed."

    return _finalize_turn(db, conversation_id, reply, tool_calls, ui_actions, quiz)


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
    for qm in db.scalars(
        select(models.ChatMessage).where(
            models.ChatMessage.conversation_id == conversation_id,
            models.ChatMessage.role == "quiz",
        )
    ).all():
        calls = list(qm.tool_calls or [])
        if calls and isinstance(calls[0], dict):
            args = dict(calls[0].get("args") or {})
            if args.get("assessment_id") == assessment_id:
                calls[0] = {**calls[0], "args": {**args, "completed": True}}
                qm.tool_calls = calls
    db.commit()

    history = db.scalars(
        select(models.ChatMessage)
        .where(models.ChatMessage.conversation_id == conversation_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(20)
    ).all()
    transcript = "\n".join(
        f"{'Student' if m.role == 'user' else 'Tutor'}: {m.content}"
        for m in reversed(history)
        if m.role in ("user", "assistant")
    )
    snapshot = build_snapshot(db, user_id)
    messages = [
        {"role": "system", "content": f"{TUTOR_PROMPT}\n\n{QUIZ_DEBRIEF_PROMPT}\n\nLEARNER SNAPSHOT: {snapshot}"},
        {"role": "user", "content": (
            f"CONVERSATION SO FAR:\n{transcript}\n\n"
            "=== HIDDEN QUIZ RESULTS (the student cannot see this — "
            "never quote scores, feedback, or rubrics) ===\n"
            f"{summary}\n\nWrite your debrief recommendation now."
        )},
    ]
    return _run_tool_loop(db, user_id, conversation_id, messages)


async def stream_tutor_turn(db, user_id: int, conversation_id: int | None, message: str,
                          ui_context: dict | None = None):
    """Streaming twin of run_tutor_turn. Yields event dicts:
    {"type": "tool", "tool", "args", "result_preview"},
    {"type": "token", "text"}, then {"type": "done", ...} (same shape as
    run_tutor_turn's return). Persists both messages like the sync version.
    """
    conversation_id, messages = _open_turn(db, user_id, conversation_id, message, ui_context)
    tools = openai_tools()
    tool_calls: list[dict] = []
    ui_actions: list[dict] = []
    quiz: dict | None = None
    seen: set[str] = set()  # exact-duplicate (tool, args) calls run once per turn
    reply = ""
    for _ in range(MAX_TOOL_ROUNDS):
        content_parts: list[str] = []
        calls: list[dict] = []
        async for kind, payload in chat_stream(messages, tools=tools):
            if kind == "token":
                content_parts.append(payload)
                yield {"type": "token", "text": payload}
            elif kind == "done":
                reply = payload["content"]
                calls = payload["tool_calls"]
        messages.append(
            {"role": "assistant", "content": reply or None, "tool_calls": calls or None}
        )
        if not calls:
            if not reply.strip() and not tool_calls:
                messages.append(
                    {"role": "user", "content": "Please respond with text, or a tool call if one fits."}
                )
                continue
            break
        for call in calls:
            name, args = _parse_call(call)
            key = _dedupe_key(name, args)
            if key in seen:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id"),
                        "content": json.dumps({"duplicate": True, "cached": True}),
                    }
                )
                continue
            seen.add(key)
            result, ui_action = await _aexecute_call(db, user_id, name, args)
            preview = _preview(result)
            tool_calls.append({"tool": name, "args": args, "result_preview": preview})
            yield {"type": "tool", "tool": name, "args": args, "result_preview": preview}
            if quiz is None:
                quiz = _capture_quiz(name, result)
            if ui_action is not None:
                ui_actions.append(ui_action)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result)[:4000],
                }
            )
    else:
        reply = reply or "Let me know how you'd like to proceed."

    yield {"type": "done", **_finalize_turn(db, conversation_id, reply, tool_calls, ui_actions, quiz)}
