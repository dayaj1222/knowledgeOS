"""Regression: PUT /proficiency must not double-insert.

The session runs with autoflush OFF, so after ProficiencyService.record()
creates a pending row, re-querying misses it and a naive handler creates a
SECOND row -> unique clash on (user_id, topic_id). The handler must reuse
the returned row. Runs the real router function on in-memory SQLite.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.models import Base
from app.routers.topics import upsert_proficiency
from app.schemas import ProficiencyUpdate


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(models.User(id=1, name="S", email="s@t"))
    db.add(models.Course(id=1, user_id=1, name="C", code="C"))
    db.add(models.Module(id=1, course_id=1, name="M"))
    db.add(models.Topic(id=1, module_id=1, name="T"))
    db.commit()
    return db


def test_put_fresh_then_update_no_clash():
    db = _db()
    r1 = upsert_proficiency(1, 1, ProficiencyUpdate(score=0.6), db)
    assert r1["data"]["score"] == 0.6
    r2 = upsert_proficiency(
        1, 1, ProficiencyUpdate(score=0.8, weak_points=["x"]), db
    )
    assert r2["data"]["score"] == 0.8
    assert r2["data"]["weak_points"] == ["x"]
    assert db.query(models.Proficiency).count() == 1  # exactly one row
    events = db.query(models.ProficiencyEvent).order_by(models.ProficiencyEvent.id).all()
    assert [(e.source, e.old_score, e.new_score) for e in events] == [
        ("manual_override", 0.0, 0.6),
        ("manual_override", 0.6, 0.8),
    ]
