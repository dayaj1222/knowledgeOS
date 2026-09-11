"""Eval: scheduler orders weak + urgent topics first, with reasons.

Runs against a real in-memory SQLite DB (faithful joins, no mocks).
Golden rule: a weak high-priority topic with a near deadline outranks a
mastered low-priority one — and every item explains itself.
"""

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.models import Base
from app.services.schedule_service import ScheduleService


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(models.User(id=1, name="S", email="s@t"))
    db.add(models.Course(id=1, user_id=1, name="C", code="C"))
    db.add(models.Module(id=1, course_id=1, name="M"))
    db.add(models.Topic(id=1, module_id=1, name="WeakUrgent", priority=5))
    db.add(models.Topic(id=2, module_id=1, name="MasteredChill", priority=1))
    db.add(models.Proficiency(user_id=1, topic_id=1, score=0.2))
    db.add(models.Proficiency(user_id=1, topic_id=2, score=0.95))
    db.add(models.Deadline(
        user_id=1, course_id=1, topic_id=1, title="CAT-2",
        due_date=datetime.now() + timedelta(days=3), weight=1.0,
    ))
    db.commit()
    return db


def test_weak_urgent_outranks_mastered():
    scored = ScheduleService.score_topics(_db(), 1, datetime.now())
    assert [s.topic.id for s in scored] == [1, 2]


def test_every_item_has_reasons():
    scored = ScheduleService.score_topics(_db(), 1, datetime.now())
    by_id = {s.topic.id: s for s in scored}
    assert any("weak mastery" in r for r in by_id[1].reasons)
    assert any("CAT-2" in r for r in by_id[1].reasons)
    assert any("solid mastery" in r for r in by_id[2].reasons)
    for s in scored:
        assert s.reasons, f"topic {s.topic.id} has no reasons"
        assert abs(
            s.components["mastery"] + s.components["priority"] + s.components["deadline"]
            - s.need
        ) < 1e-3
