"""Study-log service: closes the loop between plans and proficiency.

StudyLog records actual study events (not just quiz attempts). Logging a
session nudges proficiency slightly toward the learner's self-reported
confidence — real studying moves mastery, quizzes measure it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from .proficiency_service import STUDY_LOG, ProficiencyService
from .review_service import ReviewService, score_to_quality


class StudyService:
    @staticmethod
    def log_study(
        db: Session,
        *,
        user_id: int,
        topic_id: int,
        minutes_spent: int,
        confidence_after: float | None = None,
        resource_id: int | None = None,
        passage_id: int | None = None,
        plan_id: int | None = None,
    ) -> models.StudyLog:
        log = models.StudyLog(
            user_id=user_id,
            topic_id=topic_id,
            minutes_spent=minutes_spent,
            confidence_after=confidence_after,
            resource_id=resource_id,
            passage_id=passage_id,
            plan_id=plan_id,
        )
        db.add(log)

        if confidence_after is not None:
            db.flush()  # log.id must exist for the ledger ref
            ProficiencyService.record(
                db,
                user_id=user_id,
                topic_id=topic_id,
                observed=confidence_after,
                alpha=settings.proficiency.study_alpha,
                source=STUDY_LOG,
                ref_id=log.id,
            )
            # A study session is also a recall event for the schedule.
            ReviewService.record_result(
                db,
                user_id=user_id,
                topic_id=topic_id,
                quality=score_to_quality(confidence_after),
                source="study",
            )

        # Completing a log against a plan marks that plan done.
        if plan_id is not None:
            plan = db.get(models.Plan, plan_id)
            if plan is not None and plan.status == "pending":
                plan.status = "done"

        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def list_logs(db: Session, user_id: int) -> list[models.StudyLog]:
        return list(
            db.scalars(
                select(models.StudyLog)
                .where(models.StudyLog.user_id == user_id)
                .order_by(models.StudyLog.created_at.desc())
            ).all()
        )
