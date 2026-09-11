"""Tutor chat endpoints (non-streamed JSON v1)."""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from .. import models, schemas
from ..agent.tutor import run_quiz_debrief, run_tutor_turn, stream_tutor_turn
from ..database import SessionLocal, get_db
from ..protocol import ok

router = APIRouter(prefix="/api", tags=["chat"])

# SQLite has a single writer; a background extraction commit can collide with
# a chat turn. Retry the whole turn on a FRESH session (the failed session is
# poisoned with a pending-rollback transaction and must be discarded).
_RETRYABLE = (OperationalError, PendingRollbackError, StaleDataError)


@router.post("/chat")
def chat(body: schemas.ChatRequest, db: Session = Depends(get_db)):
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            result = run_tutor_turn(
                db, body.user_id, body.conversation_id, body.message, body.ui_context
            )
            return ok(result)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        except _RETRYABLE as e:
            last_error = e
            db.close()
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                db = SessionLocal()
    raise HTTPException(503, f"Database busy, try again: {last_error}")


@router.post("/chat/stream")
async def chat_stream(body: schemas.ChatRequest):
    """SSE twin of POST /api/chat. Events (JSON per `data:` frame):
    {"type": "token", "text"} — reply deltas as they arrive;
    {"type": "tool", "tool", "args", "result_preview"} — each executed call;
    {"type": "done", ...} — same payload as the non-streamed endpoint.
    A fresh session is used (streaming holds it open across awaits); on a
    mid-stream DB error an {"type": "error"} frame is sent instead.
    """
    import json as _json

    from sse_starlette.sse import EventSourceResponse

    db = SessionLocal()

    async def gen():
        try:
            async for event in stream_tutor_turn(
                db, body.user_id, body.conversation_id, body.message, body.ui_context
            ):
                yield {"event": event["type"], "data": _json.dumps(event)}
        except ValueError as e:
            yield {"event": "error", "data": _json.dumps({"error": str(e)})}
        except Exception as e:  # noqa: BLE001 — mid-stream errors become a frame
            try:
                db.rollback()
            except Exception:  # noqa: BLE001, S110
                pass
            yield {"event": "error", "data": _json.dumps({"error": f"{type(e).__name__}: {e}"})}
        finally:
            db.close()

    return EventSourceResponse(gen())


@router.post("/chat/quiz/submit")
def submit_chat_quiz(body: schemas.ChatQuizSubmit, db: Session = Depends(get_db)):
    """Finish an in-chat quiz: the per-card answers were already graded
    silently via /api/attempts; this runs the hidden tutor debrief and returns
    ONLY the recommendation (same shape as a normal chat turn)."""
    try:
        result = run_quiz_debrief(
            db, body.user_id, body.conversation_id, body.assessment_id
        )
        return ok(result)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/status")
def engine_status(db: Session = Depends(get_db)):
    """Real engine facts for the Settings screen: model, endpoint mode,
    threading state, database reachability, and library counts. No dummy."""
    from .. import ai

    forced = ai._THREAD_FORCED
    if forced in ("1", "true", "yes", "on"):
        threading = "forced-on"
    elif forced in ("0", "false", "no", "off"):
        threading = "forced-off"
    elif not ai._THREAD_OK:
        threading = "latched-off"
    elif ai._threading_allowed():
        threading = "proxy-sticky"
    else:
        threading = "stateless"
    try:
        n_courses = db.scalar(
            select(func.count(models.Course.id))
        ) or 0
        n_topics = db.scalar(
            select(func.count(models.Topic.id))
        ) or 0
        n_conversations = db.scalar(
            select(func.count(models.Conversation.id))
        ) or 0
        db_ok = True
    except Exception:  # noqa: BLE001 — status must never 500
        n_courses = n_topics = n_conversations = 0
        db_ok = False
    return ok({
        "model": ai.LLM_MODEL,
        "endpoint": ai.LLM_BASE_URL,
        "threading": threading,
        "database": "connected" if db_ok else "unreachable",
        "courses": n_courses,
        "topics": n_topics,
        "conversations": n_conversations,
    })


@router.delete("/users/{user_id}/conversations")
def clear_conversations(user_id: int, db: Session = Depends(get_db)):
    """Delete ALL conversations (and their messages via cascade) for a user."""
    convs = db.scalars(
        select(models.Conversation).where(models.Conversation.user_id == user_id)
    ).all()
    n = len(convs)
    for c in convs:
        db.delete(c)
    db.commit()
    return ok({"deleted": n})


@router.get("/users/{user_id}/conversations")
def list_conversations(user_id: int, db: Session = Depends(get_db)):
    convs = db.scalars(
        select(models.Conversation)
        .where(models.Conversation.user_id == user_id)
        .order_by(models.Conversation.id.desc())
        .limit(30)
    ).all()
    return ok([{"id": c.id, "title": c.title} for c in convs])


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: int, db: Session = Depends(get_db)):
    """Thread in display order: user/assistant messages with their cards
    interleaved directly after the assistant message each card follows
    (anchored by cards.message_id; unanchored cards trail at the end)."""
    msgs = db.scalars(
        select(models.ChatMessage)
        .where(models.ChatMessage.conversation_id == conversation_id)
        .order_by(models.ChatMessage.id)
    ).all()
    cards = db.scalars(
        select(models.Card)
        .where(models.Card.conversation_id == conversation_id)
        .order_by(models.Card.id)
    ).all()
    by_anchor: dict[int | None, list] = {}
    for c in cards:
        by_anchor.setdefault(c.message_id, []).append(c)
    out: list[dict] = []
    for m in msgs:
        out.append(
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )
        for c in by_anchor.pop(m.id, []):
            out.append({
                "id": c.id,
                "role": "card",
                "content": "",
                "card": {"kind": c.kind, "payload": c.payload},
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })
    for c in [c for rest in by_anchor.values() for c in rest]:
        out.append({
            "id": c.id,
            "role": "card",
            "content": "",
            "card": {"kind": c.kind, "payload": c.payload},
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
    return ok(out)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)):
    conv = db.get(models.Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    db.delete(conv)
    db.commit()
    return ok({"deleted": True, "id": conversation_id})


class _Rename(BaseModel):
    title: str


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: int, body: _Rename, db: Session = Depends(get_db)
):
    conv = db.get(models.Conversation, conversation_id)
    if conv is None:
        raise HTTPException(404, "Conversation not found")
    conv.title = body.title.strip()[:120] or conv.title
    db.commit()
    return ok({"id": conv.id, "title": conv.title})


@router.get("/users/{user_id}/memories")
def list_memories(user_id: int, db: Session = Depends(get_db)):
    mems = db.scalars(
        select(models.TutorMemory).where(models.TutorMemory.user_id == user_id)
    ).all()
    return ok([{"id": m.id, "key": m.key, "value": m.value} for m in mems])


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    mem = db.get(models.TutorMemory, memory_id)
    if mem is None:
        raise HTTPException(404, "Memory not found")
    db.delete(mem)
    db.commit()
    return ok({"deleted": True, "id": memory_id})
