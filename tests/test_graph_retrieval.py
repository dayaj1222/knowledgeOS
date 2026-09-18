"""Pinned-module retrieval must not break the turn (regression).

_rank_pool already returns formatted hit dicts; the graph node must use
them directly instead of unpacking them as (passage, match) tuples —
that raised "too many values to unpack (expected 2, got 7)".
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models
from app.agent import graph
from app.models import Base


def _db():
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(models.User(id=1, name="S", email="s@t"))
    db.commit()
    db.add(models.Course(id=1, user_id=1, name="C", code="C"))
    db.commit()
    db.add(models.Module(id=1, course_id=1, name="M"))
    db.commit()
    db.add(models.Conversation(id=1, user_id=1, title="t", module_id=1))
    db.commit()
    db.add(models.Resource(id=1, user_id=1, course_id=1, name="r",
                           type="pdf", file_path="x", module_id=1, status="done"))
    db.commit()
    db.add(models.Passage(id=1, resource_id=1,
                          content="stacks are LIFO data structures", index_order=0))
    db.commit()
    return db


def test_retrieval_node_returns_hits_without_unpack_error():
    db = _db()
    out = graph._retrieval_node({
        "db": db, "user_id": 1, "conversation_id": 1,
        "message": "what is a stack?", "messages": [],
    })
    assert len(out["retrieval"]) == 1
    assert out["retrieval"][0]["id"] == 1


def test_retrieval_node_unpinned_stays_empty():
    db = _db()
    db.get(models.Conversation, 1).module_id = None
    db.commit()
    assert graph._retrieval_node({
        "db": db, "user_id": 1, "conversation_id": 1,
        "message": "hi", "messages": [],
    }) == {"retrieval": []}
