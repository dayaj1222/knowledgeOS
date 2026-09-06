"""Study-plan scheduler service: deterministic, explainable topic scoring.

Study need for a topic is a weighted sum of three signals:

    need = W_PROF * (1 - proficiency_score)   # low mastery -> study more
         + W_PRIO * (priority / 5.0)          # exam importance 1..5, normalized
         + W_DEAD * deadline_pressure         # near/weighted due dates

    deadline_pressure = max(weight * DEADLINE_CAP / days_until_due, 0)
      - `weight` is Deadline.weight (0..1, importance of that deadline)
      - days_until_due = (due_date - now).days, minimum 1 day
      - past deadlines contribute 0 (already overdue -> no "pressure" signal)

Topics with no Proficiency row are treated as score=0.0 (weakest).
No ML involved; weights are tuned so a mastered low-priority topic always
ranks below a weak high-priority one.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ._helpers import get_or_404

W_PROF = 0.5
W_PRIO = 0.25
W_DEAD = 0.25
DEADLINE_CAP = 7.0  # pressure saturates for anything due within a week


class ScheduleService:
    @staticmethod
    def deadline_pressure_by_topic(
        db: Session, user_id: int, now: datetime
    ) -> dict[int, float]:
        deadlines = db.scalars(
            select(models.Deadline).where(models.Deadline.user_id == user_id)
        ).all()

        days_left: dict[int, float] = {}
        for dl in deadlines:
            if dl.due_date < now:
                days_left[dl.id] = 0.0
            else:
                days_left[dl.id] = float(max((dl.due_date - now).days, 1))

        topics = db.scalars(select(models.Topic)).all()
        topic_course = {
            t.id: t.module.course_id for t in topics if t.module is not None
        }

        pressure: dict[int, float] = {}
        for dl in deadlines:
            if days_left[dl.id] <= 0.0:
                continue
            p = dl.weight * DEADLINE_CAP / days_left[dl.id]
            if dl.topic_id is not None:
                pressure[dl.topic_id] = pressure.get(dl.topic_id, 0.0) + p
            else:
                for tid, cid in topic_course.items():
                    if cid == dl.course_id:
                        pressure[tid] = pressure.get(tid, 0.0) + p
        return pressure

    @staticmethod
    def score_topics(db: Session, user_id: int, now: datetime) -> list[tuple[float, models.Topic]]:
        """Score every schedulable topic by study need, highest first."""
        pressure = ScheduleService.deadline_pressure_by_topic(db, user_id, now)
        profs = db.scalars(
            select(models.Proficiency).where(models.Proficiency.user_id == user_id)
        ).all()
        prof_by_topic = {p.topic_id: p.score for p in profs}

        scored: list[tuple[float, models.Topic]] = []
        for topic in db.scalars(select(models.Topic)).all():
            if topic.module is None:
                continue  # only topics linked to a course are schedulable
            need = (
                W_PROF * (1.0 - prof_by_topic.get(topic.id, 0.0))
                + W_PRIO * (topic.priority / 5.0)
                + W_DEAD * pressure.get(topic.id, 0.0)
            )
            scored.append((need, topic))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored

    @staticmethod
    def generate_plan(db: Session, user_id: int) -> list[models.Plan]:
        """Score topics, fit them into free slots, replace stale pending plans."""
        if not db.get(models.User, user_id):
            from fastapi import HTTPException

            raise HTTPException(404, "User not found")

        pref = db.get(models.Preference, user_id)
        session_length = (
            pref.session_length_minutes if pref is not None else 45
        )

        scored = ScheduleService.score_topics(db, user_id, datetime.now())

        free_slots = list(
            db.scalars(
                select(models.Slot)
                .join(
                    models.Schedule,
                    models.Slot.schedule_id == models.Schedule.id,
                )
                .where(
                    models.Schedule.user_id == user_id,
                    models.Slot.type == "free",
                )
                .order_by(models.Slot.day_of_week, models.Slot.start_time)
            ).all()
        )

        db.execute(
            delete(models.Plan).where(
                models.Plan.user_id == user_id,
                models.Plan.status == "pending",
            )
        )

        plans: list[models.Plan] = []
        for _need, topic in scored:
            if not free_slots:
                break
            slot = free_slots.pop(0)
            plan = models.Plan(
                user_id=user_id,
                slot_id=slot.id,
                topic_id=topic.id,
                suggested_duration_minutes=session_length,
                status="pending",
            )
            db.add(plan)
            plans.append(plan)

        db.commit()
        for plan in plans:
            db.refresh(plan)
        return plans

    @staticmethod
    def set_plan_status(db: Session, plan_id: int, status: str) -> models.Plan:
        plan = get_or_404(db, models.Plan, plan_id, "Plan not found")
        plan.status = status
        db.commit()
        db.refresh(plan)
        return plan
