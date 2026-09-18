"""Deleting a chat thread must remove its messages and cards, not 409."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models
from app.models import Base
from app.routers.chat import _delete_conversation_rows


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
    db.add(models.ChatMessage(id=1, conversation_id=1, role="assistant", content="hi"))
    db.commit()
    db.add(models.Card(id=1, conversation_id=1, kind="todo", payload={}, message_id=1))
    db.commit()
    return db


def test_delete_conversation_with_cards_and_messages():
    db = _db()
    conv = db.get(models.Conversation, 1)
    _delete_conversation_rows(db, conv)
    db.commit()
    assert db.query(models.Conversation).count() == 0
    assert db.query(models.ChatMessage).count() == 0
    assert db.query(models.Card).count() == 0
