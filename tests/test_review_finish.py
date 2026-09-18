"""Finishing a review session stamps the card server-side (idempotent)."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models
from app.models import Base
from app.routers.schedule import _ReviewSessionFinish, finish_review_session


def _db():
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(models.User(id=1, name="S", email="s@t"))
    db.commit()
    db.add(models.Conversation(id=1, user_id=1, title="t"))
    db.commit()
    db.add(models.Conversation(id=2, user_id=1, title="other"))
    db.commit()
    db.add(models.Card(id=1, conversation_id=1, kind="review",
                       payload={"items": [{"topic_id": 1}]}, message_id=None))
    db.commit()
    db.add(models.Card(id=2, conversation_id=1, kind="quiz",
                       payload={"assessment_id": 9, "questions": []}, message_id=None))
    db.commit()
    return db


def test_finish_stamps_completed_and_is_idempotent():
    db = _db()
    out = finish_review_session(_ReviewSessionFinish(conversation_id=1, card_id=1), db)
    assert out["data"] == {"finished": True, "id": 1}
    assert db.get(models.Card, 1).payload["completed"] is True
    out2 = finish_review_session(_ReviewSessionFinish(conversation_id=1, card_id=1), db)
    assert out2["data"] == {"finished": True, "id": 1}


def test_finish_rejects_wrong_conversation_and_kind():
    db = _db()
    with pytest.raises(HTTPException):
        finish_review_session(_ReviewSessionFinish(conversation_id=2, card_id=1), db)
    with pytest.raises(HTTPException):
        finish_review_session(_ReviewSessionFinish(conversation_id=1, card_id=2), db)
    with pytest.raises(HTTPException):
        finish_review_session(_ReviewSessionFinish(conversation_id=1, card_id=999), db)
