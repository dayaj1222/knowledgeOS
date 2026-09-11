"""Schedule, Slot, Deadline, Plan, and StudyLog endpoints.

Thin HTTP layer — scoring and plan generation live in
ScheduleService, study logging in StudyService.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..protocol import ok
from ..services.review_service import ReviewService
from ..services.schedule_service import ScheduleService
from ..services.study_service import StudyService

router = APIRouter(prefix="/api", tags=["schedule"])


def _dump(schema_cls, obj):
    return schema_cls.model_validate(obj).model_dump(mode="json")


# ---- Schedules ----
@router.post("/users/{user_id}/schedules", status_code=201)
def create_schedule(user_id: int, payload: schemas.ScheduleCreate, db: Session = Depends(get_db)):
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    schedule = models.Schedule(user_id=user_id, **payload.model_dump(exclude={"user_id"}))
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return ok(_dump(schemas.ScheduleOut, schedule))


@router.get("/users/{user_id}/schedules")
def list_schedules(user_id: int, db: Session = Depends(get_db)):
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    rows = db.scalars(
        select(models.Schedule).where(models.Schedule.user_id == user_id)
    ).all()
    return ok([_dump(schemas.ScheduleOut, r) for r in rows])


# ---- Slots ----
@router.post("/schedules/{schedule_id}/slots", status_code=201)
def create_slot(schedule_id: int, payload: schemas.SlotCreate, db: Session = Depends(get_db)):
    if not db.get(models.Schedule, schedule_id):
        raise HTTPException(404, "Schedule not found")
    slot = models.Slot(schedule_id=schedule_id, **payload.model_dump(exclude={"schedule_id"}))
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return ok(_dump(schemas.SlotOut, slot))


@router.get("/schedules/{schedule_id}/slots")
def list_slots(schedule_id: int, db: Session = Depends(get_db)):
    if not db.get(models.Schedule, schedule_id):
        raise HTTPException(404, "Schedule not found")
    rows = db.scalars(
        select(models.Slot)
        .where(models.Slot.schedule_id == schedule_id)
        .order_by(models.Slot.day_of_week, models.Slot.start_time)
    ).all()
    return ok([_dump(schemas.SlotOut, r) for r in rows])


@router.delete("/slots/{slot_id}", status_code=200)
def delete_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.get(models.Slot, slot_id)
    if not slot:
        raise HTTPException(404, "Slot not found")
    db.delete(slot)
    db.commit()
    return ok({"deleted": True, "id": slot_id})


# ---- Deadlines ----
@router.post("/deadlines", status_code=201)
def create_deadline(payload: schemas.DeadlineCreate, db: Session = Depends(get_db)):
    if not db.get(models.User, payload.user_id):
        raise HTTPException(404, "User not found")
    if not db.get(models.Course, payload.course_id):
        raise HTTPException(404, "Course not found")
    if payload.topic_id is not None and not db.get(models.Topic, payload.topic_id):
        raise HTTPException(404, "Topic not found")
    deadline = models.Deadline(**payload.model_dump())
    db.add(deadline)
    db.commit()
    db.refresh(deadline)
    return ok(_dump(schemas.DeadlineOut, deadline))


@router.get("/users/{user_id}/deadlines")
def list_deadlines(user_id: int, db: Session = Depends(get_db)):
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    rows = db.scalars(
        select(models.Deadline)
        .where(models.Deadline.user_id == user_id)
        .order_by(models.Deadline.due_date)
    ).all()
    return ok([_dump(schemas.DeadlineOut, r) for r in rows])


# ---- Plans ----
@router.get("/users/{user_id}/plans")
def list_plans(user_id: int, db: Session = Depends(get_db)):
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    rows = db.scalars(
        select(models.Plan)
        .where(models.Plan.user_id == user_id)
        .order_by(models.Plan.generated_at.desc())
    ).all()
    return ok([_dump(schemas.PlanOut, r) for r in rows])


@router.post(
    "/users/{user_id}/generate-plan",
    status_code=201,
)
def generate_plan(user_id: int, db: Session = Depends(get_db)):
    """Score topics by study need and write pending Plan rows (see ScheduleService)."""
    plans = ScheduleService.generate_plan(db, user_id)
    return ok([_dump(schemas.PlanOut, p) for p in plans])


@router.get("/users/{user_id}/plan-reasons")
def plan_reasons(user_id: int, db: Session = Depends(get_db)):
    """Why-plan: scored topics with human-readable reasons (no writes)."""
    from datetime import datetime

    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    return ok([
        {
            "topic_id": s.topic.id,
            "topic_name": s.topic.name,
            "need": s.need,
            "reasons": s.reasons,
            "components": s.components,
        }
        for s in ScheduleService.score_topics(db, user_id, datetime.now())
    ])


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, payload: schemas.PlanUpdate, db: Session = Depends(get_db)):
    """Mark a plan done/skipped (or reopen to pending)."""
    plan = ScheduleService.set_plan_status(db, plan_id, payload.status)
    return ok(_dump(schemas.PlanOut, plan))


# ---- Study logs (close the plan -> proficiency loop) ----
@router.post("/study-logs", status_code=201)
def create_study_log(payload: schemas.StudyLogCreate, db: Session = Depends(get_db)):
    if not db.get(models.User, payload.user_id):
        raise HTTPException(404, "User not found")
    if not db.get(models.Topic, payload.topic_id):
        raise HTTPException(404, "Topic not found")
    return ok(_dump(schemas.StudyLogOut, StudyService.log_study(db, **payload.model_dump())))


@router.get("/users/{user_id}/study-logs")
def list_study_logs(user_id: int, db: Session = Depends(get_db)):
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    return ok([_dump(schemas.StudyLogOut, log) for log in StudyService.list_logs(db, user_id)])


# ---- Spaced repetition ----
@router.get("/users/{user_id}/reviews/due")
def due_reviews(user_id: int, limit: int = 20, db: Session = Depends(get_db)):
    """Topics due for review now, oldest first (SM-2 schedule)."""
    if not db.get(models.User, user_id):
        raise HTTPException(404, "User not found")
    return ok(ReviewService.due_queue(db, user_id, limit=limit))


@router.post("/reviews/result", status_code=201)
def submit_review_result(payload: schemas.ReviewResultCreate, db: Session = Depends(get_db)):
    """Record a manual recall result (e.g. self-reviewed flashcards)."""
    if not db.get(models.User, payload.user_id):
        raise HTTPException(404, "User not found")
    if not db.get(models.Topic, payload.topic_id):
        raise HTTPException(404, "Topic not found")
    review = ReviewService.record_result(
        db,
        user_id=payload.user_id,
        topic_id=payload.topic_id,
        quality=payload.quality,
        source="review",
    )
    db.commit()
    db.refresh(review)
    return ok({
        "topic_id": review.topic_id,
        "due_date": review.due_date.isoformat(),
        "interval_days": review.interval_days,
        "ease_factor": review.ease_factor,
    })
