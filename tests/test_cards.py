"""Cards registry: capture mapping, slim shapes, validation, migration."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.agent import cards as C
from app.models import Base


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_capture_maps_each_trigger():
    assert C.capture("generate_quiz", {"type": "assessment", "assessment_id": 1,
                                       "questions": [{"id": 1}]})[0] == "quiz"
    assert C.capture("ask_clarify", {"question": "q?"})[0] == "clarify"
    assert C.capture("ask_review", {"items": [1]})[0] == "review"
    assert C.capture("update_todo", {"type": "todo", "todos": [{"content": "a"}]})[0] == "todo"
    assert C.capture("find_videos", {"videos": [{"video_id": "x"}]})[0] == "video"
    assert C.capture("start_timer", {"action": "start"})[0] == "timer"
    assert C.capture("get_passages", {"x": 1}) is None
    assert C.capture("generate_quiz", {"type": "assessment", "questions": []}) is None


def test_slim_keeps_exact_turn_shapes():
    quiz = C.slim("quiz", {"type": "assessment", "assessment_id": 3, "questions": [1],
                           "created": True, "count": 1, "hint": "x"})
    assert quiz == {"assessment_id": 3, "questions": [1]}
    todo = C.slim("todo", {"type": "todo", "todos": [{"content": "a", "status": "pending"}]})
    assert todo == {"todos": todo["todos"], "total": 1, "completed": 0,
                    "current": None, "current_active": None}
    timer = C.slim("timer", {"type": "timer", "action": "stop"})
    assert timer == {"action": "stop"}


def test_validate_rejects_unknown_and_bad_keys():
    with pytest.raises(ValueError):
        C.validate("poll", {})
    with pytest.raises(ValueError):
        C.validate("quiz", {"assessment_id": 1})  # missing questions


def test_migrate_legacy_messages():
    db = _db()
    db.add(models.Conversation(id=1, user_id=1, title="t"))
    db.add(models.ChatMessage(id=1, conversation_id=1, role="user", content="hi"))
    db.add(models.ChatMessage(id=2, conversation_id=1, role="assistant", content="ok"))
    db.add(models.ChatMessage(
        id=3, conversation_id=1, role="todo", content="",
        tool_calls=[{"tool": "todo", "args": {"type": "todo", "todos": [{"content": "a"}],
                                             "total": 1, "completed": 0}}],
    ))
    db.commit()
    assert C.migrate_legacy_cards(db) == 1
    cards = C.list_cards(db, 1)
    assert len(cards) == 1 and cards[0].kind == "todo"
    assert cards[0].payload["todos"] == [{"content": "a"}]
    remaining = [m.role for m in db.query(models.ChatMessage).all()]
    assert "todo" not in remaining
    # idempotent rerun moves nothing
    assert C.migrate_legacy_cards(db) == 0


def test_persist_anchors_display_order():
    db = _db()
    db.add(models.Conversation(id=1, user_id=1, title="t"))
    db.commit()
    c = C.persist_card(db, 1, "video", {"videos": []}, message_id=42)
    assert c.message_id == 42
