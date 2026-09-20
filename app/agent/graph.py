"""LangGraph orchestration for tutor turns — the canonical tutor lifecycle.

Lifecycle: open_turn -> retrieval -> planning -> validation -> model
<-> tools -> finalize.  The async variant emits SSE events from graph nodes.
The model/tools cycle is a real graph loop (not a Python for-loop in
tutor.py), so tracing, budgets, and future retrieval/planning nodes attach
to explicit nodes. tutor.py keeps persistence/prompt helpers; this module
owns turn orchestration for both JSON and SSE setup paths.
"""

from __future__ import annotations

import logging as _logging
import time as _time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

_log = _logging.getLogger("knowledge-base.tutor")


class TutorTurnState(TypedDict, total=False):
    """State passed between tutor lifecycle nodes."""

    db: Any
    user_id: int
    conversation_id: int | None
    message: str
    ui_context: dict | None
    images: list[str] | None
    messages: list[dict]
    thread_id: str | None
    tools: list[dict]
    result: dict
    # Loop state
    tool_calls: list[dict]
    ui_actions: list[dict]
    cards: dict[str, dict]
    seen_keys: list[str]
    reply_parts: list[str]
    pending_calls: list[dict]
    rounds_left: int
    nudged: bool
    retrieval: list[dict]
    plan_status: str
    validation: dict


def _open_turn_node(state: TutorTurnState) -> dict:
    # Local imports avoid a tutor <-> graph import cycle at module load.
    from .tutor import MAX_TOOL_ROUNDS, _open_turn, openai_tools_shim

    conversation_id, messages, thread_id = _open_turn(
        state["db"], state["user_id"], state.get("conversation_id"),
        state["message"], state.get("ui_context"), state.get("images"),
    )
    return {
        "conversation_id": conversation_id,
        "messages": messages,
        "thread_id": thread_id,
        "tools": openai_tools_shim(),
        "tool_calls": [],
        "ui_actions": [],
        "cards": {},
        "seen_keys": [],
        "reply_parts": [],
        "pending_calls": [],
        "rounds_left": MAX_TOOL_ROUNDS,
        "nudged": False,
    }


def _init_loop_state(
    db: Any, user_id: int, conversation_id: int,
    messages: list[dict], thread_id: str | None, tools: list[dict],
) -> TutorTurnState:
    from .tutor import MAX_TOOL_ROUNDS

    return {
        "db": db,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "messages": messages,
        "thread_id": thread_id,
        "tools": tools,
        "tool_calls": [],
        "ui_actions": [],
        "cards": {},
        "seen_keys": [],
        "reply_parts": [],
        "pending_calls": [],
        "rounds_left": MAX_TOOL_ROUNDS,
        "nudged": False,
        "retrieval": [],
        "plan_status": "not-applicable",
        "validation": {},
    }


def _latest_user_text(messages: list[dict]) -> str:
    """Return the current user text without trying to serialize image parts."""
    for item in reversed(messages):
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(part.get("text", "")) for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
    return ""


def _retrieval_node(state: TutorTurnState) -> dict:
    """Retrieve a compact grounding pack for the pinned module, if any.

    Unpinned turns deliberately remain tool-driven: guessing a module here
    would violate the tutor's module-scoping rule.  Results stay in graph
    state for tracing and are injected into the current model context below.
    """
    from .. import models
    from .tutor_tools import _module_pool, _rank_pool

    conv = state["db"].get(models.Conversation, state.get("conversation_id"))
    module_id = getattr(conv, "module_id", None)
    if module_id is None:
        return {"retrieval": []}
    passages, module = _module_pool(state["db"], module_id)
    if module is None:
        return {"retrieval": []}
    query = state.get("message") or _latest_user_text(state.get("messages", []))
    try:
        # _rank_pool already returns formatted hit dicts (not tuples).
        hits = _rank_pool(state["db"], str(query), passages, 3)
    except Exception:  # Retrieval is a helpful context enhancement, never a turn failure.
        _log.exception("tutor.retrieval failed conversation=%s", state.get("conversation_id"))
        hits = []
    retrieval = list(hits)
    _log.info("tutor.retrieval conversation=%s module=%s hits=%d",
              state.get("conversation_id"), module_id, len(retrieval))
    return {"retrieval": retrieval}


def _planning_node(state: TutorTurnState) -> dict:
    """Expose active-plan state as a first-class, observable graph stage."""
    from .tutor import _todo_line

    plan = _todo_line(state["db"], state["conversation_id"])
    status = "active" if "[ACTIVE STUDY PLAN]" in plan and "no active plan" not in plan else "none"
    return {"plan_status": status}


def _validation_node(state: TutorTurnState) -> dict:
    """Validate model inputs before each invocation, without mutating tools."""
    tools = state.get("tools", [])
    valid_tools = [tool for tool in tools if isinstance(tool, dict) and tool.get("function")]
    validation = {
        "tool_count": len(valid_tools),
        "has_messages": bool(state.get("messages")),
        "retrieval_hits": len(state.get("retrieval", [])),
    }
    if len(valid_tools) != len(tools):
        _log.warning("tutor.validation omitted malformed tools conversation=%s",
                     state.get("conversation_id"))
    return {"tools": valid_tools, "validation": validation}


def _model_messages(state: TutorTurnState) -> list[dict]:
    """Add graph-produced retrieval context only to the model's ephemeral input."""
    messages = list(state.get("messages", []))
    retrieval = state.get("retrieval", [])
    if not retrieval:
        return messages
    citations = "\n".join(
        f"- chunk {hit['id']} ({hit['section'] or 'untitled'}): {hit['content']}"
        for hit in retrieval
    )
    context = "\n\nTURN RETRIEVAL (ground answers here; cite chunk IDs when used):\n" + citations
    # Keep the stable system prompt first.  The provider expects tool results
    # to immediately follow their assistant call, so a trailing system message
    # is not a safe way to add per-turn context on later loop rounds.
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") != "user":
            continue
        user_message = dict(messages[index])
        content = user_message.get("content")
        if isinstance(content, str):
            user_message["content"] = content + context
        elif isinstance(content, list):
            parts = [dict(part) if isinstance(part, dict) else part for part in content]
            for part in parts:
                if isinstance(part, dict) and part.get("type") == "text":
                    part["text"] = str(part.get("text", "")) + context
                    break
            user_message["content"] = parts
        else:
            continue
        messages[index] = user_message
        break
    return messages


def _model_node(state: TutorTurnState) -> dict:
    import asyncio

    from . import tutor as tutor_mod

    chat_with_tools = tutor_mod.chat_with_tools

    messages = list(state.get("messages", []))
    reply_parts = list(state.get("reply_parts", []))
    msg = asyncio.run(chat_with_tools(
        _model_messages(state), tools=state.get("tools", []),
        temperature=0.4, thread_id=state.get("thread_id"),
    ))
    calls = msg.get("tool_calls") or []
    content = str(msg.get("content") or "")
    _log.info(
        "tutor.model conversation=%s tools=%d content_chars=%d",
        state.get("conversation_id"), len(calls), len(content),
    )
    if content.strip():
        reply_parts.append(content)
    messages.append({
        "role": "assistant",
        "content": content or None,
        "tool_calls": calls or None,
    })
    return {
        "messages": messages,
        "reply_parts": reply_parts,
        "pending_calls": calls,
        "rounds_left": int(state.get("rounds_left", 1)) - 1,
        "retrieval": [],
    }


async def _stream_model_node(state: TutorTurnState) -> dict:
    """Async model node which publishes token deltas through LangGraph."""
    from langgraph.config import get_stream_writer

    from . import tutor as tutor_mod

    writer = get_stream_writer()
    content_parts: list[str] = []
    calls: list[dict] = []
    async for kind, payload in tutor_mod.chat_stream(
        _model_messages(state), tools=state.get("tools", []),
        thread_id=state.get("thread_id"),
    ):
        if kind == "token":
            text = str(payload)
            content_parts.append(text)
            writer({"type": "token", "text": text})
        elif kind == "done":
            content = str(payload.get("content") or "")
            if content:
                content_parts = [content]
            calls = payload.get("tool_calls") or []
    content = "".join(content_parts)
    messages = list(state.get("messages", []))
    reply_parts = list(state.get("reply_parts", []))
    if content.strip():
        reply_parts.append(content)
    messages.append({"role": "assistant", "content": content or None,
                     "tool_calls": calls or None})
    _log.info("tutor.stream_model conversation=%s tools=%d content_chars=%d",
              state.get("conversation_id"), len(calls), len(content))
    return {
        "messages": messages,
        "reply_parts": reply_parts,
        "pending_calls": calls,
        "rounds_left": int(state.get("rounds_left", 1)) - 1,
        "retrieval": [],
    }


async def _astream_retrieval_node(state: TutorTurnState) -> dict:
    """Keep synchronous SQLAlchemy access on the SSE request's event loop."""
    return _retrieval_node(state)


async def _astream_planning_node(state: TutorTurnState) -> dict:
    return _planning_node(state)


async def _astream_validation_node(state: TutorTurnState) -> dict:
    return _validation_node(state)


async def _astream_nudge_node(state: TutorTurnState) -> dict:
    return _nudge_node(state)


async def _astream_finalize_node(state: TutorTurnState) -> dict:
    return _finalize_node(state)


def _tools_node(state: TutorTurnState) -> dict:
    import json

    from . import cards as card_registry
    from .tutor import (
        _dedupe_key,
        _execute_call,
        _explicit_move_on,
        _parse_call,
        _preview,
        _todo_update_advances_current_step,
    )

    db = state["db"]
    user_id = state["user_id"]
    messages = list(state.get("messages", []))
    tool_calls = list(state.get("tool_calls", []))
    ui_actions = list(state.get("ui_actions", []))
    cards = dict(state.get("cards", {}))
    seen = set(state.get("seen_keys", []))

    for call in state.get("pending_calls", []):
        name, args = _parse_call(call)
        key = _dedupe_key(name, args)
        if key in seen:
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id"),
                "content": json.dumps({"duplicate": True, "cached": True}),
            })
            continue
        seen.add(key)
        if (
            name == "update_todo"
            and _todo_update_advances_current_step(db, state["conversation_id"], args)
            and not _explicit_move_on(str(state.get("message") or ""))
        ):
            result = {"error": "The learner did not explicitly ask to move on. Keep the current plan step active; answer or teach within it instead."}
            ui_action = None
        else:
            result, ui_action = _execute_call(db, user_id, name, args)
        tool_calls.append({"tool": name, "args": args, "result_preview": _preview(result)})
        hit = card_registry.capture(name, result)
        if hit is not None:
            kind, payload = hit
            _, first_wins = card_registry.TRIGGERS[name]
            if not first_wins or kind not in cards:
                cards[kind] = payload
        if ui_action is not None:
            ui_actions.append(ui_action)
        messages.append({
            "role": "tool",
            "tool_call_id": call.get("id"),
            "content": json.dumps(result)[:4000],
        })

    return {
        "messages": messages,
        "tool_calls": tool_calls,
        "ui_actions": ui_actions,
        "cards": cards,
        "seen_keys": sorted(seen),
        "pending_calls": [],
    }


async def _stream_tools_node(state: TutorTurnState) -> dict:
    """Async tool node; it is the sole producer of streamed tool events."""
    import json

    from langgraph.config import get_stream_writer

    from . import cards as card_registry
    from .tutor import (
        _aexecute_call,
        _dedupe_key,
        _explicit_move_on,
        _parse_call,
        _preview,
        _todo_update_advances_current_step,
    )

    writer = get_stream_writer()
    messages = list(state.get("messages", []))
    tool_calls = list(state.get("tool_calls", []))
    ui_actions = list(state.get("ui_actions", []))
    cards = dict(state.get("cards", {}))
    seen = set(state.get("seen_keys", []))
    for call in state.get("pending_calls", []):
        name, args = _parse_call(call)
        key = _dedupe_key(name, args)
        if key in seen:
            messages.append({"role": "tool", "tool_call_id": call.get("id"),
                             "content": json.dumps({"duplicate": True, "cached": True})})
            continue
        seen.add(key)
        if (
            name == "update_todo"
            and _todo_update_advances_current_step(state["db"], state["conversation_id"], args)
            and not _explicit_move_on(str(state.get("message") or ""))
        ):
            result = {"error": "The learner did not explicitly ask to move on. Keep the current plan step active; answer or teach within it instead."}
            ui_action = None
        else:
            result, ui_action = await _aexecute_call(state["db"], state["user_id"], name, args)
        preview = _preview(result)
        tool_calls.append({"tool": name, "args": args, "result_preview": preview})
        writer({"type": "tool", "tool": name, "args": args, "result_preview": preview})
        hit = card_registry.capture(name, result)
        if hit is not None:
            kind, payload = hit
            _, first_wins = card_registry.TRIGGERS[name]
            if not first_wins or kind not in cards:
                cards[kind] = payload
        if ui_action is not None:
            ui_actions.append(ui_action)
        messages.append({"role": "tool", "tool_call_id": call.get("id"),
                         "content": json.dumps(result)[:4000]})
    return {"messages": messages, "tool_calls": tool_calls, "ui_actions": ui_actions,
            "cards": cards, "seen_keys": sorted(seen), "pending_calls": []}


def _finalize_node(state: TutorTurnState) -> dict:
    from .tutor import _finalize_turn

    reply_parts = list(state.get("reply_parts", []))
    if not reply_parts:
        reply_parts = ["Let me know how you'd like to proceed."]
    result = _finalize_turn(
        state["db"], state["conversation_id"],
        "\n\n".join(reply_parts),
        list(state.get("tool_calls", [])),
        list(state.get("ui_actions", [])),
        dict(state.get("cards", {})),
    )
    return {"result": result, "pending_calls": []}


def _route_after_model(state: TutorTurnState) -> str:
    pending = state.get("pending_calls", [])
    if pending:
        if int(state.get("rounds_left", 0)) > 0:
            return "tools"
        return "finalize"
    # No tool calls: done unless this was a completely empty turn.
    if state.get("reply_parts") or state.get("tool_calls"):
        return "finalize"
    if not state.get("nudged"):
        return "nudge"
    return "finalize"


def _nudge_node(state: TutorTurnState) -> dict:
    messages = list(state.get("messages", []))
    messages.append({
        "role": "user",
        "content": "Please respond with text, or a tool call if one fits.",
    })
    return {"messages": messages, "nudged": True}


def _route_after_tools(state: TutorTurnState) -> str:
    if int(state.get("rounds_left", 0)) > 0:
        return "model"
    return "finalize"


async def _astream_route_after_model(state: TutorTurnState) -> str:
    return _route_after_model(state)


async def _astream_route_after_tools(state: TutorTurnState) -> str:
    return _route_after_tools(state)


def _build_loop_graph():
    graph = StateGraph(TutorTurnState)
    graph.add_node("retrieval", _retrieval_node)
    graph.add_node("planning", _planning_node)
    graph.add_node("validation", _validation_node)
    graph.add_node("model", _model_node)
    graph.add_node("tools", _tools_node)
    graph.add_node("nudge", _nudge_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_edge(START, "retrieval")
    graph.add_edge("retrieval", "planning")
    graph.add_edge("planning", "validation")
    graph.add_edge("validation", "model")
    graph.add_conditional_edges("model", _route_after_model, {
        "tools": "tools", "finalize": "finalize", "nudge": "nudge",
    })
    graph.add_edge("nudge", "validation")
    graph.add_conditional_edges("tools", _route_after_tools, {
        "model": "validation", "finalize": "finalize",
    })
    graph.add_edge("finalize", END)
    return graph.compile()


_loop_graph = _build_loop_graph()


def _build_stream_loop_graph():
    """Async graph equivalent of the JSON loop; custom stream events are SSE."""
    graph = StateGraph(TutorTurnState)
    graph.add_node("retrieval", _astream_retrieval_node)
    graph.add_node("planning", _astream_planning_node)
    graph.add_node("validation", _astream_validation_node)
    graph.add_node("model", _stream_model_node)
    graph.add_node("tools", _stream_tools_node)
    graph.add_node("nudge", _astream_nudge_node)
    graph.add_node("finalize", _astream_finalize_node)
    graph.add_edge(START, "retrieval")
    graph.add_edge("retrieval", "planning")
    graph.add_edge("planning", "validation")
    graph.add_edge("validation", "model")
    graph.add_conditional_edges("model", _astream_route_after_model, {
        "tools": "tools", "finalize": "finalize", "nudge": "nudge",
    })
    graph.add_edge("nudge", "validation")
    graph.add_conditional_edges("tools", _astream_route_after_tools, {
        "model": "validation", "finalize": "finalize",
    })
    graph.add_edge("finalize", END)
    return graph.compile()


_stream_loop_graph = _build_stream_loop_graph()


def _turn_summary(state: TutorTurnState) -> str:
    return (
        f"conversation={state.get('conversation_id')} "
        f"tool_calls={len(state.get('tool_calls', []))} "
        f"ui_actions={len(state.get('ui_actions', []))} "
        f"cards={sorted(state.get('cards', {}))} "
        f"reply_chars={sum(len(p) for p in state.get('reply_parts', []))}"
    )


def run_agent_loop(
    db: Any, user_id: int, conversation_id: int,
    messages: list[dict], thread_id: str | None, tools: list[dict],
) -> dict:
    """Run the canonical model<->tools loop; returns the finalized payload."""
    from .tutor import current_conversation

    token = current_conversation.set(conversation_id)
    try:
        started = _time.perf_counter()
        state = _loop_graph.invoke(_init_loop_state(
            db, user_id, conversation_id, messages, thread_id, tools,
        ))
        _log.info("tutor.turn done %s elapsed=%.2fs", _turn_summary(state), _time.perf_counter() - started)
        return state["result"]
    finally:
        current_conversation.reset(token)


async def stream_agent_loop(
    db: Any, user_id: int, conversation_id: int,
    messages: list[dict], thread_id: str | None, tools: list[dict],
):
    """Yield graph-native token/tool events followed by the turn payload."""
    from .tutor import current_conversation

    token = current_conversation.set(conversation_id)
    final_state: TutorTurnState | None = None
    try:
        initial = _init_loop_state(db, user_id, conversation_id, messages, thread_id, tools)
        async for mode, chunk in _stream_loop_graph.astream(
            initial, stream_mode=["custom", "values"],
        ):
            if mode == "custom":
                yield chunk
            elif mode == "values" and isinstance(chunk, dict) and chunk.get("result"):
                final_state = chunk
        if final_state is None:
            raise RuntimeError("Tutor stream graph finished without a result")
        yield {"type": "done", **final_state["result"]}
    finally:
        current_conversation.reset(token)


def _build_tutor_graph():
    graph = StateGraph(TutorTurnState)
    graph.add_node("open_turn", _open_turn_node)
    graph.add_node("retrieval", _retrieval_node)
    graph.add_node("planning", _planning_node)
    graph.add_node("validation", _validation_node)
    graph.add_node("model", _model_node)
    graph.add_node("tools", _tools_node)
    graph.add_node("nudge", _nudge_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_edge(START, "open_turn")
    graph.add_edge("open_turn", "retrieval")
    graph.add_edge("retrieval", "planning")
    graph.add_edge("planning", "validation")
    graph.add_edge("validation", "model")
    graph.add_conditional_edges("model", _route_after_model, {
        "tools": "tools", "finalize": "finalize", "nudge": "nudge",
    })
    graph.add_edge("nudge", "validation")
    graph.add_conditional_edges("tools", _route_after_tools, {
        "model": "validation", "finalize": "finalize",
    })
    graph.add_edge("finalize", END)
    return graph.compile()


tutor_graph = _build_tutor_graph()


def _build_open_turn_graph():
    """Shared lifecycle prefix for both JSON and SSE tutor endpoints."""
    graph = StateGraph(TutorTurnState)
    graph.add_node("open_turn", _open_turn_node)
    graph.add_edge(START, "open_turn")
    graph.add_edge("open_turn", END)
    return graph.compile()


open_turn_graph = _build_open_turn_graph()


def run_graph_turn(
    db: Any,
    user_id: int,
    conversation_id: int | None,
    message: str,
    ui_context: dict | None = None,
    images: list[str] | None = None,
) -> dict:
    """Run the LangGraph-backed turn and return the established API payload."""
    from .tutor import current_conversation

    # open_turn persists the user message outside the loop's conversation pin;
    # set the pin around the whole graph so convo-scoped tools resolve.
    # The pin needs the real id, so do open first via the shared subgraph,
    # then run the loop with the pin held (same as the legacy wrapper did).
    opened = open_turn_graph.invoke({
        "db": db,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message": message,
        "ui_context": ui_context,
        "images": images,
    })
    token = current_conversation.set(opened["conversation_id"])
    try:
        state = _loop_graph.invoke({
            "db": db,
            "user_id": user_id,
            "conversation_id": opened["conversation_id"],
            "messages": opened["messages"],
            "thread_id": opened.get("thread_id"),
            "tools": opened.get("tools", []),
            "tool_calls": [],
            "ui_actions": [],
            "cards": {},
            "seen_keys": [],
            "reply_parts": [],
            "pending_calls": [],
            "rounds_left": opened.get("rounds_left", 8),
            "nudged": False,
        })
        return state["result"]
    finally:
        current_conversation.reset(token)


def open_graph_turn(
    db: Any,
    user_id: int,
    conversation_id: int | None,
    message: str,
    ui_context: dict | None = None,
    images: list[str] | None = None,
) -> tuple[int, list[dict], str]:
    """Run the graph-owned turn setup shared by sync and streaming paths."""
    state = open_turn_graph.invoke({
        "db": db,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "message": message,
        "ui_context": ui_context,
        "images": images,
    })
    return state["conversation_id"], state["messages"], state["thread_id"]
