"""Persisted extraction jobs resume after an interrupted process."""

from fastapi import BackgroundTasks
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import models
from app.routers import resources


def _db():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        models.User(id=1, name="Student", email="student@example.test"),
        models.Course(id=2, user_id=1, name="Course", code="C"),
        models.Resource(
            id=3, user_id=1, course_id=2, name="Notes", type="pdf",
            file_path="storage/uploads/3/notes.pdf", status="done",
        ),
    ])
    db.commit()
    return db


def test_startup_requeues_interrupted_extraction(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        models.User(id=1, name="Student", email="student@example.test"),
        models.Course(id=2, user_id=1, name="Course", code="C"),
        models.Resource(
            id=3, user_id=1, course_id=2, name="Notes", type="pdf",
            file_path="storage/uploads/3/notes.pdf", status="processing",
        ),
        models.ExtractionJob(resource_id=3, status="running", attempts=1),
    ])
    db.commit()

    # The real worker runs in a separate thread; capture the scheduled work
    # while keeping this regression test deterministic.
    started: list[tuple] = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            started.append((target, args, daemon))

        def start(self):
            return None

    monkeypatch.setattr(resources, "SessionLocal", lambda: db)
    monkeypatch.setattr(resources.threading, "Thread", FakeThread)

    resources.resume_pending_extractions()

    db.expire_all()
    job = db.scalar(select(models.ExtractionJob).where(models.ExtractionJob.resource_id == 3))
    assert job.status == "queued"
    assert started == [(resources._extract, (3,), True)]


def test_reextract_removes_old_embeddings_and_resets_job():
    db = _db()
    passage = models.Passage(resource_id=3, content="old", index_order=0)
    db.add(passage)
    db.flush()
    db.add_all([
        models.PassageEmbedding(passage_id=passage.id, model="test", vec=b"old"),
        models.ExtractionJob(
            resource_id=3, status="failed", attempts=3, max_attempts=3,
            error="old failure",
        ),
    ])
    db.commit()

    result = resources.re_extract(3, BackgroundTasks(), db)

    assert result["data"]["status"] == "processing"
    assert db.scalar(select(models.Passage).where(models.Passage.resource_id == 3)) is None
    assert db.scalar(select(models.PassageEmbedding)) is None
    job = db.scalar(select(models.ExtractionJob).where(models.ExtractionJob.resource_id == 3))
    assert job.status == "queued"
    assert job.cancel_requested is False
    assert job.next_attempt_at is None


def test_cancel_queued_job_marks_resource_terminal():
    db = _db()
    db.add(models.ExtractionJob(resource_id=3, status="queued"))
    db.commit()

    result = resources.cancel_extraction(3, db)

    assert result["data"]["job"]["status"] == "cancelled"
    assert db.get(models.Resource, 3).status == "cancelled"


def test_failed_extraction_is_requeued_with_backoff(monkeypatch):
    db = _db()
    db.add(models.ExtractionJob(resource_id=3, status="queued", max_attempts=3))
    db.commit()
    scheduled: list[tuple[int, float]] = []

    def fail_extract(resource_id: int) -> None:
        resource = db.get(models.Resource, resource_id)
        resource.status = "failed"
        resource.error = "temporary extractor failure"
        db.commit()

    monkeypatch.setattr(resources, "SessionLocal", lambda: db)
    monkeypatch.setattr(resources, "_extract_locked", fail_extract)
    monkeypatch.setattr(resources, "_schedule_extract", lambda resource_id, delay: scheduled.append((resource_id, delay)))

    resources._extract(3)

    job = db.scalar(select(models.ExtractionJob).where(models.ExtractionJob.resource_id == 3))
    assert job.status == "queued"
    assert job.attempts == 1
    assert job.next_attempt_at is not None
    assert scheduled == [(3, resources.RETRY_BASE_SECONDS)]
