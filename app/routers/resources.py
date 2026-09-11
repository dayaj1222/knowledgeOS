"""Resource + Passage endpoints, with the upload → extract → chunk pipeline.

Uses the standard response envelope (app.protocol) and ASYNC extraction:
- POST upload saves the file, creates the Resource, and kicks extraction in a
  background task, returning 202 immediately.
- The client polls GET /api/resources/{id}/status until the status is terminal
  (done / partial / failed).
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..agent import parse_syllabus
from ..database import SessionLocal, get_db
from ..ingest import chunk_text, extract_text, save_upload
from ..ingest.tagger import assign_passages
from ..protocol import TERMINAL_STATUSES, fail, ok

router = APIRouter(prefix="/api", tags=["resources"])

# Extractions run through the SAME single-file pipeline one at a time.
# Concurrent _extract tasks collide on CPU-heavy OCR subprocesses and on
# SQLite's single writer ("database is locked"), which is what made
# multi-file uploads fail to parse. NOTE: this serializes within one
# process; run a single uvicorn worker (no --workers N).
_EXTRACT_LOCK = threading.Lock()


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
        _extract_locked(resource_id)


def _extract_locked(resource_id: int) -> None:
    db = SessionLocal()
    try:
        res = db.get(models.Resource, resource_id)
        if not res:
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

        # Tag passages to topics if the resource is module-scoped.
        if res.module_id is not None:
            _tag_passages(res, db)

        res.status = "done"
        res.error = None
        db.commit()
    finally:
        db.close()


def _tag_passages(res: models.Resource, db: Session) -> None:
    """Deterministically assign each passage to one topic in the resource's
    module (name+description term scoring, no LLM). Unmatched passages keep
    topic_id NULL — visible as untagged, never force-filed."""
    topics = db.scalars(
        select(models.Topic).where(models.Topic.module_id == res.module_id)
    ).all()
    if not topics:
        return

    passages = db.scalars(
        select(models.Passage)
        .where(models.Passage.resource_id == res.id)
        .order_by(models.Passage.index_order)
    ).all()

    assigned = assign_passages(
        [
            {"id": p.id, "content": p.content, "section_path": p.section_path or ""}
            for p in passages
        ],
        [
            {"id": t.id, "name": t.name, "description": t.description or ""}
            for t in topics
        ],
    )
    by_id = {p.id: p for p in passages}
    for pid, result in assigned.items():
        p = by_id.get(int(pid))
        if p is not None:
            p.topic_id = result["primary"]
            p.tag_confidence = result["confidence"]
            p.extra_topic_ids = result["extras"]


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
    if not db.get(models.Course, course_id):
        return fail("not_found", "Course not found", status_code=404)
    if not db.get(models.User, user_id):
        return fail("not_found", "User not found", status_code=404)
    if module_id is not None and not db.get(models.Module, module_id):
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

    return ok({
        "resource_id": res.id,
        "status": res.status,
    })


@router.post("/resources/{resource_id}/extract", status_code=202)
def re_extract(resource_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Re-run extraction (async): delete old passages, re-extract fresh."""
    res = db.get(models.Resource, resource_id)
    if not res:
        return fail("not_found", "Resource not found", status_code=404)
    for p in list(res.passages):
        db.delete(p)
    res.status = "processing"
    db.commit()
    background.add_task(_extract, resource_id)
    return ok({"resource_id": resource_id, "status": "processing"})


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
    })


# ---- read endpoints (wrapped in the envelope too) ----
@router.get("/courses/{course_id}/resources")
def list_resources(course_id: int, db: Session = Depends(get_db)):
    resources = db.scalars(
        select(models.Resource).where(models.Resource.course_id == course_id)
    ).all()
    return ok([
        {
            "id": r.id,
            "course_id": r.course_id,
            "name": r.name,
            "type": r.type,
            "status": r.status,
            "error": r.error,
            "module_id": r.module_id,
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
