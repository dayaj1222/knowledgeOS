"""Question + Assessment + Attempt endpoints (standard envelope).

Quiz generation is a SINGLE endpoint: POST /quiz/generate takes
{topic_ids, questions_per_topic, difficulty, instructions} — a one-element
topic_ids list is the "single topic" case. The question -> answer loop
writes back to Proficiency via QuizService.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..protocol import ok
from ..services.course_service import CourseService
from ..services.quiz_service import QuizService
from ..services.review_service import ReviewService, score_to_quality

router = APIRouter(prefix="/api", tags=["questions"])


def _dump(schema_cls, obj):
    return schema_cls.model_validate(obj).model_dump(mode="json")


# ---- Questions ----
@router.post("/topics/{topic_id}/questions", status_code=201)
def create_question(topic_id: int, payload: schemas.QuestionCreate, db: Session = Depends(get_db)):
    CourseService.require_topic(db, topic_id)
    q = models.Question(topic_id=topic_id, **payload.model_dump(exclude={"topic_id"}))
    db.add(q)
    db.commit()
    db.refresh(q)
    return ok(_dump(schemas.QuestionOut, q))


@router.get("/topics/{topic_id}/questions")
def list_questions(topic_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(models.Question).where(models.Question.topic_id == topic_id)
    ).all()
    return ok([_dump(schemas.QuestionOut, q) for q in rows])


# ---- Quiz generation (single endpoint; one or many topics) ----
@router.post("/quiz/generate", status_code=201)
def generate_quiz(payload: schemas.QuizGenerateRequest, db: Session = Depends(get_db)):
    """Generate + persist questions for the given topics.

    Returns the created questions so the frontend can offer a "Take quiz" step
    without regenerating. Questions are a permanent DB addition, not transient.
    """
    created = QuizService.generate_quiz(
        db,
        payload.topic_ids,
        payload.questions_per_topic,
        payload.difficulty,
        payload.instructions,
    )
    return ok([_dump(schemas.QuestionOut, q) for q in created])


# ---- Assessments ----
@router.post("/assessments", status_code=201)
def create_assessment(payload: schemas.AssessmentCreate, db: Session = Depends(get_db)):
    a = models.Assessment(**payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return ok(_dump(schemas.AssessmentOut, a))


@router.get("/assessments/{assessment_id}")
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    a = db.get(models.Assessment, assessment_id)
    if not a:
        raise HTTPException(404, "Assessment not found")
    links = db.scalars(
        select(models.AssessmentQuestion)
        .where(models.AssessmentQuestion.assessment_id == assessment_id)
        .order_by(models.AssessmentQuestion.order_index)
    ).all()
    questions = [db.get(models.Question, link.question_id) for link in links]
    payload = _dump(schemas.AssessmentOut, a)
    payload["questions"] = [
        _dump(schemas.QuestionOut, q) for q in questions if q is not None
    ]
    return ok(payload)


class _AssessmentPatch(BaseModel):
    status: str


@router.patch("/assessments/{assessment_id}")
def patch_assessment(
    assessment_id: int, body: _AssessmentPatch, db: Session = Depends(get_db)
):
    a = db.get(models.Assessment, assessment_id)
    if not a:
        raise HTTPException(404, "Assessment not found")
    if body.status not in ("generating", "ready", "in_progress", "completed", "abandoned"):
        raise HTTPException(422, "Invalid status")
    a.status = body.status
    if body.status == "completed":
        from datetime import datetime

        a.completed_at = datetime.now()
    db.commit()
    db.refresh(a)
    return ok(_dump(schemas.AssessmentOut, a))


@router.delete("/assessments/{assessment_id}")
def delete_assessment(assessment_id: int, db: Session = Depends(get_db)):
    a = db.get(models.Assessment, assessment_id)
    if not a:
        raise HTTPException(404, "Assessment not found")
    # Links go; the questions stay in the per-topic bank.
    db.execute(
        delete(models.AssessmentQuestion).where(
            models.AssessmentQuestion.assessment_id == assessment_id
        )
    )
    db.delete(a)
    db.commit()
    return ok({"deleted": True, "id": assessment_id})


# ---- Attempts ----
@router.post("/attempts", status_code=201)
def create_attempt(payload: schemas.AttemptCreate, db: Session = Depends(get_db)):
    attempt = models.Attempt(**payload.model_dump())
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return ok(_dump(schemas.AttemptOut, attempt))


@router.patch("/attempts/{attempt_id}/grade")
async def grade_attempt(attempt_id: int, payload: schemas.AttemptGrade, db: Session = Depends(get_db)):
    """Grade server-side (LLM, else keyword overlap); never trust client scores.

    If the client does NOT supply an explicit score (score is None), compute it
    from the question's expected_key_points vs the user_answer.
    """
    attempt = db.get(models.Attempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Attempt not found")
    if payload.user_answer is not None:
        # Re-grade in place (in-chat quiz card edits): the SAME attempt is
        # updated so proficiency/SM-2 don't double-count duplicates.
        attempt.user_answer = payload.user_answer
    question = db.get(models.Question, attempt.question_id)

    score = payload.score
    feedback = payload.feedback
    matched = []
    missed = []
    if score is None and question is not None:
        # Awaited LLM grading (meaning-based 0.0–1.0 + feedback). Proficiency,
        # SM-2 rescheduling, and weak-point sync below all consume THIS score.
        score, feedback, matched, missed = await QuizService.agrade_answer(
            db, question, attempt.user_answer or ""
        )

    attempt.score = score if score is not None else 0.0
    attempt.feedback = feedback
    attempt.matched_key_points = matched
    attempt.missed_key_points = missed
    attempt.status = payload.status
    attempt.excluded = payload.excluded
    if question and not payload.excluded:
        QuizService.fold_attempt_into_proficiency(db, attempt, question.topic_id)
        # Every graded answer is a recall event: reschedule + refresh gaps.
        ReviewService.record_result(
            db,
            user_id=attempt.user_id,
            topic_id=question.topic_id,
            quality=score_to_quality(attempt.score),
        )
        QuizService.sync_weak_points(
            db, user_id=attempt.user_id, topic_id=question.topic_id
        )
    db.commit()
    db.refresh(attempt)
    return ok(_dump(schemas.AttemptOut, attempt))


# ---- Weakness diagnosis + targeted drills ----
@router.get("/users/{user_id}/weaknesses")
def list_weaknesses(user_id: int, db: Session = Depends(get_db)):
    """Per-topic miss aggregation, worst first (see QuizService)."""
    return ok(QuizService.topic_weaknesses(db, user_id))


@router.post("/quiz/drill", status_code=201)
def generate_drill(payload: schemas.DrillRequest, db: Session = Depends(get_db)):
    """Generate questions aimed at the learner's known gaps."""
    created = QuizService.generate_drill(
        db,
        payload.user_id,
        topic_id=payload.topic_id,
        count=payload.count,
        difficulty=payload.difficulty,
    )
    return ok([_dump(schemas.QuestionOut, q) for q in created])
