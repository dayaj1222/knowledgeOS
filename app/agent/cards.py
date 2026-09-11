"""Inline cards: the registry between tool results and chat UI.

A card is one renderable unit (quiz | clarify | review | todo | video) with
a validated payload dict. Rules:
- capture: each triggering tool maps its result to a payload (or None).
- kinds are closed: CARD_KINDS. Unknown kinds never persist.
- payloads carry the keys in REQUIRED_KEYS; violations raise (our own
  constructors guarantee them — a failure is a wiring bug, not user input).
- legacy role='quiz'|... ChatMessage rows migrate once via migrate_cards().

Adding a card = one entry here (kind + keys + trigger tools) + one frontend
renderer in the card registry. No other file changes.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models

log = logging.getLogger(__name__)

CARD_KINDS = ("quiz", "clarify", "review", "todo", "video")

# Trigger tool -> (card kind, first-wins?). todo is last-wins (plan evolves);
# the rest keep the turn's first payload.
TRIGGERS: dict[str, tuple[str, bool]] = {
    "generate_quiz": ("quiz", True),
    "ask_clarify": ("clarify", True),
    "ask_review": ("review", True),
    "start_timer": ("timer", True),  # transient: returned, never persisted
    "stop_timer": ("timer", True),
    "update_todo": ("todo", False),
    "find_videos": ("video", True),
}

# Persisted kinds only (timer rides the turn payload, not the DB).
PERSISTED_KINDS = ("quiz", "clarify", "review", "todo", "video")

REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "quiz": ("assessment_id", "questions"),
    "clarify": ("question",),
    "review": ("items",),
    "todo": ("todos",),
    "video": ("videos",),
}


def slim(kind: str, payload: dict) -> dict:
    """Reduce a validated payload to the exact turn/message shape the
    frontend contract expects (extra tool-result keys never leak)."""
    if kind == "quiz":
        return {"assessment_id": payload["assessment_id"], "questions": payload["questions"]}
    if kind == "clarify":
        return {
            "question": payload.get("question", ""),
            "options": payload.get("options", []) or [],
            "allow_free_text": payload.get("allow_free_text", True),
        }
    if kind == "review":
        return {"items": payload.get("items", [])}
    if kind == "todo":
        todos = payload.get("todos", [])
        return {
            "todos": todos,
            "total": payload.get("total", len(todos)),
            "completed": payload.get(
                "completed", sum(1 for t in todos if t.get("status") == "completed")
            ),
            "current": payload.get("current"),
            "current_active": payload.get("current_active"),
        }
    if kind == "video":
        return {"videos": payload.get("videos", [])}
    if kind == "timer":
        out: dict = {"action": payload.get("action")}
        if payload.get("action") == "start":
            out.update({
                "topic_id": payload.get("topic_id"),
                "topic_name": payload.get("topic_name", ""),
                "label": payload.get("label", ""),
            })
        return out
    raise ValueError(f"unknown card kind '{kind}'")


def validate(kind: str, payload: dict) -> dict:
    """Reject unknown kinds and key-violating payloads."""
    if kind not in PERSISTED_KINDS:
        raise ValueError(f"unknown card kind '{kind}'")
    if not isinstance(payload, dict):
        raise ValueError(f"card '{kind}' payload must be an object")
    missing = [k for k in REQUIRED_KEYS[kind] if k not in payload]
    if missing:
        raise ValueError(f"card '{kind}' missing keys: {missing}")
    return payload


def capture(tool_name: str, result) -> tuple[str, dict] | None:
    """Map a tool result to (kind, payload). None when not a card."""
    spec = TRIGGERS.get(tool_name)
    if spec is None or not isinstance(result, dict):
        return None
    kind, _first_wins = spec
    inner = {k: v for k, v in result.items() if k != "hint"}
    if kind == "quiz" and (result.get("type") != "assessment" or not result.get("questions")):
        return None
    if kind == "clarify" and not result.get("question"):
        return None
    if kind == "review" and not result.get("items"):
        return None
    if kind == "todo" and (result.get("type") != "todo" or not result.get("todos")):
        return None
    if kind == "video" and not result.get("videos"):
        return None
    if kind == "timer" and result.get("action") not in ("start", "stop"):
        return None
    payload = {"type": kind, **{k: v for k, v in inner.items() if k != "type"}}
    return kind, payload


def persist_card(
    db: Session, conversation_id: int, kind: str, payload: dict,
    message_id: int | None = None,
) -> models.Card:
    """Validate + store one card. Returns the row.

    message_id anchors display order: the assistant message this card
    follows (cards render directly after it).
    """
    validate(kind, payload)
    card = models.Card(
        conversation_id=conversation_id, kind=kind,
        payload=slim(kind, payload), message_id=message_id,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def list_cards(db: Session, conversation_id: int) -> list[models.Card]:
    return list(
        db.scalars(
            select(models.Card)
            .where(models.Card.conversation_id == conversation_id)
            .order_by(models.Card.id)
        ).all()
    )


def migrate_legacy_cards(db: Session) -> int:
    """One-time: role='quiz'|... messages → cards rows. Idempotent."""
    moved = 0
    rows = db.scalars(
        select(models.ChatMessage).where(models.ChatMessage.role.in_(PERSISTED_KINDS))
    ).all()
    for m in rows:
        try:
            calls = m.tool_calls or []
            args = calls[0].get("args") if calls and isinstance(calls[0], dict) else None
            if not isinstance(args, dict):
                continue
            validate(m.role, args)
            db.add(models.Card(conversation_id=m.conversation_id, kind=m.role, payload=args))
            db.delete(m)
            moved += 1
        except ValueError as e:
            log.warning("Skipping unmigratable %s message %s: %s", m.role, m.id, e)
    if moved:
        db.commit()
    return moved
