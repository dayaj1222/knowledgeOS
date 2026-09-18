"""Resource + Passage endpoints, with the upload → extract → chunk pipeline.

Uses the standard response envelope (app.protocol) and ASYNC extraction:
- POST upload saves the file, creates the Resource, and kicks extraction in a
  background task, returning 202 immediately.
- The client polls GET /api/resources/{id}/status until the status is terminal
  (done / partial / failed).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import models
from ..agent import parse_syllabus
from ..database import SessionLocal, get_db
from ..ingest import chunk_text, extract_text, save_upload
from ..protocol import TERMINAL_STATUSES, fail, ok

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["resources"])

# Extractions run through the SAME single-file pipeline one at a time.
# Concurrent _extract tasks collide on CPU-heavy OCR subprocesses and on
# SQLite's single writer ("database is locked"), which is what made
# multi-file uploads fail to parse. NOTE: this serializes within one
# process; run a single uvicorn worker (no --workers N).
_EXTRACT_LOCK = threading.Lock()
MAX_EXTRACTION_ATTEMPTS = 3
RETRY_BASE_SECONDS = 5


def _job_payload(job: models.ExtractionJob | None) -> dict | None:
    """Public, intentionally small durable-queue view."""
    if job is None:
        return None
    return {
        "id": job.id,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "next_attempt_at": job.next_attempt_at.isoformat() if job.next_attempt_at else None,
        "cancel_requested": job.cancel_requested,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _schedule_extract(resource_id: int, delay_seconds: float = 0) -> None:
    """Schedule work locally while its durable job remains the source of truth."""
    if delay_seconds <= 0:
        threading.Thread(target=_extract, args=(resource_id,), daemon=True).start()
        return
    timer = threading.Timer(delay_seconds, _extract, args=(resource_id,))
    timer.daemon = True
    timer.start()


@router.post("/courses/{course_id}/syllabus", status_code=201)
def upload_syllabus(
    course_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a syllabus PDF → LLM parses modules+topics → saved to DB.

    Synchronous endpoint: the LLM call (run_sync) blocks, and FastAPI runs sync
    `def` endpoints in a threadpool, avoiding an event-loop conflict.
    """
    course = db.get(models.Course, course_id)
    if not course:
        return fail("not_found", "Course not found", status_code=404)

    data = file.file.read()
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        text, _, _ = extract_text(tmp_path, "pdf")
    finally:
        tmp_path.unlink(missing_ok=True)

    if not text.strip():
        return fail("extract_failed", "Could not read text from syllabus PDF", status_code=422)

    structure = parse_syllabus(text)

    created_modules = []
    for m in structure.modules:
        mod = models.Module(course_id=course_id, name=m.module, order_index=len(created_modules))
        db.add(mod)
        db.flush()  # get mod.id for topics
        created_modules.append({"module_id": mod.id, "module": m.module, "topics": []})
        for t in m.topics:
            topic = models.Topic(
                module_id=mod.id,
                name=t.name,
                description=t.description or "",
                order_index=len(created_modules[-1]["topics"]),
            )
            db.add(topic)
            db.flush()
            created_modules[-1]["topics"].append({"topic_id": topic.id, "name": t.name})

    db.commit()
    return ok({"modules": created_modules})


def _extract(resource_id: int) -> None:
    """Run extraction in a fresh session (background task), updating status."""
    with _EXTRACT_LOCK:
        db = SessionLocal()
        try:
            job = db.scalar(
                select(models.ExtractionJob).where(
                    models.ExtractionJob.resource_id == resource_id
                )
            )
            if job is not None:
                if job.cancel_requested or job.status == "cancelled":
                    job.status = "cancelled"
                    job.finished_at = datetime.now()
                    resource = db.get(models.Resource, resource_id)
                    if resource is not None:
                        resource.status = "cancelled"
                    db.commit()
                    return
                if job.next_attempt_at and job.next_attempt_at > datetime.now():
                    return
                job.status = "running"
                job.attempts += 1
                job.started_at = datetime.now()
                job.error = None
                db.commit()
        finally:
            db.close()
        _extract_locked(resource_id)
        db = SessionLocal()
        try:
            job = db.scalar(select(models.ExtractionJob).where(
                models.ExtractionJob.resource_id == resource_id
            ))
            resource = db.get(models.Resource, resource_id)
            if job is None:
                return
            if job.cancel_requested:
                job.status = "cancelled"
                job.finished_at = datetime.now()
                if resource is not None:
                    resource.status = "cancelled"
            elif resource and resource.status == "done":
                job.status = "completed"
                job.error = None
                job.finished_at = datetime.now()
                job.next_attempt_at = None
            else:
                job.error = resource.error if resource else "resource_missing"
                if job.attempts < job.max_attempts:
                    delay = RETRY_BASE_SECONDS * (2 ** (job.attempts - 1))
                    job.status = "queued"
                    job.next_attempt_at = datetime.now() + timedelta(seconds=delay)
                    db.commit()
                    _schedule_extract(resource_id, delay)
                    return
                job.status = "failed"
                job.finished_at = datetime.now()
            db.commit()
        finally:
            db.close()


def resume_pending_extractions() -> None:
    """Resume queued/interrupted jobs after a server restart (one local worker)."""
    db = SessionLocal()
    try:
        jobs = db.scalars(select(models.ExtractionJob).where(
            models.ExtractionJob.status.in_(("queued", "running")),
            models.ExtractionJob.cancel_requested.is_(False),
        )).all()
        for job in jobs:
            job.status = "queued"
        db.commit()
        ids = [job.resource_id for job in jobs]
    finally:
        db.close()
    for resource_id in ids:
        _schedule_extract(resource_id)


def _extract_locked(resource_id: int) -> None:
    db = SessionLocal()
    try:
        res = db.get(models.Resource, resource_id)
        if not res:
            return
        job = db.scalar(select(models.ExtractionJob).where(
            models.ExtractionJob.resource_id == resource_id
        ))
        if job is not None and job.cancel_requested:
            res.status = "cancelled"
            db.commit()
            return

        abs_path = Path(__file__).resolve().parent.parent.parent / res.file_path
        if not abs_path.exists():
            res.status = "failed"
            res.error = "file_missing"
            db.commit()
            return

        res.status = "processing"
        db.commit()

        try:
            text, status, pages = extract_text(abs_path, res.type)
        except Exception as e:  # noqa: BLE001
            res.status = "failed"
            res.error = f"extract_error: {e}"
            db.commit()
            return

        if status == "failed" or not text.strip():
            res.status = "failed"
            res.error = "empty_extract" if status == "empty" else "extract_failed"
            db.commit()
            return

        chunks = chunk_text(text, pages)
        if not chunks:
            res.status = "failed"
            res.error = "no_chunks"
            db.commit()
            return

        if job is not None:
            db.refresh(job)
        if job is not None and job.cancel_requested:
            res.status = "cancelled"
            db.commit()
            return

        for c in chunks:
            db.add(models.Passage(
                resource_id=resource_id,
                content=c["content"],
                index_order=c["index_order"],
                section_path=c.get("section_path"),
                page_start=c.get("page_start"),
                page_end=c.get("page_end"),
            ))
        db.flush()  # get passage ids

        # Embed every chunk for module-pool vector search. Failure degrades
        # to keyword fallback — never fail the upload on embeddings.
        try:
            from ..ingest.embeddings import MODEL_NAME, embed_texts, pack

            passages = db.scalars(
                select(models.Passage)
                .where(models.Passage.resource_id == resource_id)
                .order_by(models.Passage.index_order)
            ).all()
            for p, vec in zip(passages, embed_texts([p.content for p in passages]), strict=True):
                db.add(models.PassageEmbedding(
                    passage_id=p.id, model=MODEL_NAME, vec=pack(vec),
                ))
            db.flush()
        except Exception as e:  # noqa: BLE001
            log.warning("embed resource=%s skipped: %s", resource_id, e)

        # Passages stay unfiled (topic_id NULL): retrieval is module-pool
        # vector search + ID-range expansion, never per-topic filing.
        stored = db.scalars(
            select(models.Passage).where(models.Passage.resource_id == resource_id)
        ).all()
        first_page = min((p.page_start or 0 for p in stored), default=0)
        last_page = max((p.page_end or 0 for p in stored), default=0)
        log.info(
            "extract resource=%s chunks=%d pages=%s-%s",
            resource_id, len(stored), first_page, last_page,
        )
        res.status = "done"
        res.error = None
        db.commit()
    finally:
        db.close()


@router.post("/courses/{course_id}/resources", status_code=202)
async def upload_resource(
    course_id: int,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    type: str = Form("pdf"),
    user_id: int = Form(1),
    module_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    """Multipart upload → save → 202 with resource_id; extraction runs async.

    module_id is optional (contract sends file/name/type only); when given,
    passages are LLM-tagged to that module's topics.
    """
    if not db.get(models.User, user_id):
        return fail("not_found", "User not found", status_code=404)
    course = db.get(models.Course, course_id)
    if course is None or course.user_id != user_id:
        return fail("not_found", "Course not found", status_code=404)
    if module_id is not None:
        module = db.get(models.Module, module_id)
        if module is None or module.course_id != course_id:
            return fail("not_found", "Module not found", status_code=404)

    data = await file.read()
    filename = name or file.filename or "upload"
    # Extensionless custom names break type detection downstream (extractors
    # key off suffix) — inherit the uploaded file's suffix when missing.
    orig_suffix = Path(file.filename or "").suffix
    if orig_suffix and not Path(filename).suffix:
        filename = filename + orig_suffix

    # Duplicate guard: same course + same filename (case-insensitive) means
    # this file was already uploaded — reject instead of extracting twice.
    # (This is how "Module 3 Notes.pdf" ended up three times under Embedded.)
    existing = db.scalar(
        select(models.Resource).where(
            models.Resource.course_id == course_id,
            func.lower(models.Resource.name) == filename.strip().lower(),
        )
    )
    if existing is not None:
        scope = (
            f"module {existing.module_id}" if existing.module_id is not None
            else "the course (no module)"
        )
        return fail(
            "duplicate",
            f"'{existing.name}' is already uploaded as resource "
            f"{existing.id} ({existing.status}) under {scope}. "
            "Delete it first or rename the file to upload a new copy.",
            status_code=409,
        )

    res = models.Resource(
        user_id=user_id,
        course_id=course_id,
        name=filename,
        type=type,
        module_id=module_id,
        file_path="",
        status="uploaded",
    )
    db.add(res)
    db.flush()

    try:
        rel_path = save_upload(res.id, filename, data)
    except ValueError as e:
        db.rollback()
        return fail("too_large", str(e), status_code=413)

    res.file_path = rel_path
    db.commit()
    db.refresh(res)

    # kick extraction after the response is sent
    background.add_task(_extract, res.id)
    db.add(models.ExtractionJob(
        resource_id=res.id, status="queued", max_attempts=MAX_EXTRACTION_ATTEMPTS,
    ))
    db.commit()

    return ok({
        "resource_id": res.id,
        "status": res.status,
    })


@router.post("/resources/{resource_id}/extract", status_code=202)
def re_extract(resource_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Re-run extraction after removing old chunks and their vectors."""
    res = db.get(models.Resource, resource_id)
    if not res:
        return fail("not_found", "Resource not found", status_code=404)
    passage_ids = db.scalars(select(models.Passage.id).where(
        models.Passage.resource_id == resource_id
    )).all()
    if passage_ids:
        # Do this explicitly instead of relying on ORM-loaded relationships:
        # SQLite FK enforcement may be off for databases created before v1.
        db.execute(delete(models.PassageEmbedding).where(
            models.PassageEmbedding.passage_id.in_(passage_ids)
        ))
        db.execute(delete(models.Passage).where(models.Passage.id.in_(passage_ids)))
    job = db.scalar(select(models.ExtractionJob).where(
        models.ExtractionJob.resource_id == resource_id
    ))
    if job is None:
        db.add(models.ExtractionJob(
            resource_id=resource_id, status="queued", max_attempts=MAX_EXTRACTION_ATTEMPTS,
        ))
    else:
        job.status = "queued"
        job.error = None
        job.finished_at = None
        job.next_attempt_at = None
        job.cancel_requested = False
    res.status = "processing"
    db.commit()
    background.add_task(_extract, resource_id)
    return ok({"resource_id": resource_id, "status": "processing", "job": _job_payload(job)})


@router.post("/resources/{resource_id}/extract/cancel")
def cancel_extraction(resource_id: int, db: Session = Depends(get_db)):
    """Cancel queued work, or request cancellation at the next safe boundary."""
    res = db.get(models.Resource, resource_id)
    if res is None:
        return fail("not_found", "Resource not found", status_code=404)
    job = db.scalar(select(models.ExtractionJob).where(
        models.ExtractionJob.resource_id == resource_id
    ))
    if job is None or job.status in ("completed", "failed", "cancelled"):
        return fail("not_cancellable", "No active extraction job", status_code=409)
    job.cancel_requested = True
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = datetime.now()
        res.status = "cancelled"
    db.commit()
    return ok({"resource_id": resource_id, "job": _job_payload(job)})


@router.get("/resources/{resource_id}/status")
def resource_status(resource_id: int, db: Session = Depends(get_db)):
    res = db.get(models.Resource, resource_id)
    if not res:
        return fail("not_found", "Resource not found", status_code=404)
    return ok({
        "status": res.status,
        "error": res.error,
        "passage_count": len(res.passages),
        "terminal": res.status in TERMINAL_STATUSES,
        "job": _job_payload(db.scalar(select(models.ExtractionJob).where(
            models.ExtractionJob.resource_id == resource_id
        ))),
    })


# ---- read endpoints (wrapped in the envelope too) ----
@router.get("/courses/{course_id}/resources")
def list_resources(course_id: int, db: Session = Depends(get_db)):
    resources = db.scalars(
        select(models.Resource).where(models.Resource.course_id == course_id)
    ).all()
    counts = dict(
        db.execute(
            select(models.Passage.resource_id, func.count(models.Passage.id))
            .where(models.Passage.resource_id.in_([r.id for r in resources]))
            .group_by(models.Passage.resource_id)
        ).all()
    ) if resources else {}
    jobs = {
        job.resource_id: job
        for job in db.scalars(select(models.ExtractionJob).where(
            models.ExtractionJob.resource_id.in_([r.id for r in resources])
        )).all()
    } if resources else {}
    return ok([
        {
            "id": r.id,
            "course_id": r.course_id,
            "name": r.name,
            "type": r.type,
            "status": r.status,
            "error": r.error,
            "module_id": r.module_id,
            "passage_count": counts.get(r.id, 0),
            "job": _job_payload(jobs.get(r.id)),
        }
        for r in resources
    ])


@router.get("/resources/{resource_id}/passages")
def list_passages(resource_id: int, db: Session = Depends(get_db)):
    if not db.get(models.Resource, resource_id):
        return fail("not_found", "Resource not found", status_code=404)
    passages = db.scalars(
        select(models.Passage)
        .where(models.Passage.resource_id == resource_id)
        .order_by(models.Passage.index_order)
    ).all()
    return ok([
        {
            "id": p.id,
            "content": p.content,
            "index_order": p.index_order,
            "section_path": p.section_path,
            "page_start": p.page_start,
            "page_end": p.page_end,
            "topic_id": p.topic_id,
        }
        for p in passages
    ])


# ---- passage notes (tutor + learner annotations) ----
@router.get("/passages/{passage_id}/notes")
def list_passage_notes(passage_id: int, db: Session = Depends(get_db)):
    if not db.get(models.Passage, passage_id):
        return fail("not_found", "Passage not found", status_code=404)
    notes = db.scalars(
        select(models.PassageNote)
        .where(models.PassageNote.passage_id == passage_id)
        .order_by(models.PassageNote.id)
    ).all()
    return ok([
        {
            "id": n.id,
            "passage_id": n.passage_id,
            "user_id": n.user_id,
            "note": n.note,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notes
    ])


@router.post("/passages/{passage_id}/notes")
def add_passage_note(
    passage_id: int, body: dict, db: Session = Depends(get_db)
):
    """Add a tutor/learner annotation to a passage. Body: {note, user_id?}."""
    passage = db.get(models.Passage, passage_id)
    if passage is None:
        return fail("not_found", "Passage not found", status_code=404)
    text = str((body or {}).get("note", "")).strip()
    if not text:
        return fail("bad_request", "note must be non-empty", status_code=400)
    try:
        user_id = int((body or {}).get("user_id", 1))
    except (TypeError, ValueError):
        return fail("bad_request", "user_id must be an integer", status_code=400)
    if not db.get(models.User, user_id):
        return fail("not_found", "User not found", status_code=404)
    resource = db.get(models.Resource, passage.resource_id)
    if resource is None or resource.user_id != user_id:
        return fail("not_found", "Passage not found", status_code=404)
    note = models.PassageNote(
        passage_id=passage_id, user_id=user_id, note=text[:2000]
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return ok({
        "id": note.id,
        "passage_id": note.passage_id,
        "user_id": note.user_id,
        "note": note.note,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    })


@router.delete("/passages/notes/{note_id}")
def delete_passage_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(models.PassageNote, note_id)
    if note is None:
        return fail("not_found", "Note not found", status_code=404)
    db.delete(note)
    db.commit()
    return ok({"deleted": True, "id": note_id})
