"""Turn finalization through the card registry (no LLM).

Locks: cards persist once with slim payloads, turn keys keep exact legacy
shapes, timer rides the turn without persisting, unknown kinds never reach
_finalize_turn (capture filters them).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.agent import cards as C
from app.agent.tutor import _finalize_turn
from app.models import Base


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(models.User(id=1, name="S", email="s@t"))
    db.add(models.Conversation(id=1, user_id=1, title="t"))
    db.commit()
    return db


QUIZ_RAW = {
    "type": "assessment", "created": True, "assessment_id": 7,
    "questions": [{"id": 1, "text": "q?"}], "count": 1, "hint": "x",
}
TODO_RAW = {
    "type": "todo", "todos": [{"content": "a", "status": "in_progress"}],
    "total": 1, "completed": 0, "current": "a", "hint": "x",
}


def test_finalize_persists_cards_with_slim_shapes():
    db = _db()
    out = _finalize_turn(db, 1, "reply", [], [], {"quiz": QUIZ_RAW, "todo": TODO_RAW})
    assert out["quiz"] == {"message_id": out["quiz"]["message_id"],
                           "assessment_id": 7, "questions": [{"id": 1, "text": "q?"}]}
    assert out["todo"]["total"] == 1 and out["todo"]["todos"][0]["content"] == "a"
    rows = C.list_cards(db, 1)
    assert [(c.kind, c.message_id is not None) for c in rows] == [
        ("quiz", True), ("todo", True)]
    assert rows[0].payload == {"assessment_id": 7, "questions": [{"id": 1, "text": "q?"}]}


def test_timer_rides_turn_without_persisting():
    db = _db()
    out = _finalize_turn(db, 1, "reply", [], [],
                         {"timer": {"type": "timer", "action": "stop"}})
    assert out["timer"] == {"action": "stop"}
    assert C.list_cards(db, 1) == []


def test_capture_rejects_non_cards():
    assert C.capture("record_understanding", {"recorded": True}) is None
    assert C.capture("generate_quiz", {"type": "assessment", "questions": []}) is None
