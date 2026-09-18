"""Conversation module pins: permanent until moved on the learner's words.

Contract: stamp on create from ui_context; stored pin wins every turn;
set_context re-pins/unpins with validation; tutor never touches it itself.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.agent import tutor
from app.agent.tutor_tools import current_conversation, set_context
from app.database import Base


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(models.User(id=1, name="t", email="t@t.t"))
        s.add(models.User(id=2, name="o", email="o@o.o"))
        s.add(models.Course(id=1, user_id=1, name="Nets", code="NET"))
        s.add(models.Course(id=9, user_id=2, name="Other", code="OTH"))
        s.add(models.Module(id=10, course_id=1, name="Routing"))
        s.add(models.Module(id=20, course_id=1, name="Switching"))
        s.add(models.Module(id=90, course_id=9, name="Foreign"))
        s.commit()
        yield s


def test_create_stamps_pin_from_ui_context(db):
    cid, _, _ = tutor._open_turn(db, 1, None, "hello", {"module_id": 10})
    assert db.get(models.Conversation, cid).module_id == 10


def test_create_without_pin_stays_unpinned(db):
    cid, _, _ = tutor._open_turn(db, 1, None, "hello", None)
    assert db.get(models.Conversation, cid).module_id is None


def test_create_rejects_foreign_module(db):
    cid, _, _ = tutor._open_turn(db, 1, None, "hello", {"module_id": 90})
    assert db.get(models.Conversation, cid).module_id is None


def test_set_context_repins_and_unpins(db):
    cid, _, _ = tutor._open_turn(db, 1, None, "hello", {"module_id": 10})
    token = current_conversation.set(cid)
    try:
        out = set_context(db, 1, {"module_id": 20})
        assert out == {"pinned": "Switching"}
        assert db.get(models.Conversation, cid).module_id == 20
        out = set_context(db, 1, {"module_id": None})
        assert out == {"pinned": None}
        assert db.get(models.Conversation, cid).module_id is None
    finally:
        current_conversation.reset(token)


def test_set_context_rejects_unknown_and_foreign(db):
    cid, _, _ = tutor._open_turn(db, 1, None, "hello", {"module_id": 10})
    token = current_conversation.set(cid)
    try:
        assert "error" in set_context(db, 1, {"module_id": 999})
        assert "error" in set_context(db, 1, {"module_id": 90})
        assert db.get(models.Conversation, cid).module_id == 10
    finally:
        current_conversation.reset(token)


def test_set_context_needs_active_conversation(db):
    assert set_context(db, 1, {"module_id": 10})["error"] == "no active conversation"


def test_pin_survives_later_turns(db):
    cid, _, _ = tutor._open_turn(db, 1, None, "hello", {"module_id": 10})
    # Second turn carries no ui_context — stored pin must persist untouched.
    cid2, _, _ = tutor._open_turn(db, 1, cid, "again", None)
    assert cid2 == cid
    assert db.get(models.Conversation, cid).module_id == 10
