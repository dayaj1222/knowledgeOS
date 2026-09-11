"""Study-plan scheduler service: deterministic, explainable topic scoring.

Study need for a topic is a weighted sum of three signals (weights live in
config [scheduler], tunable without code edits):

    need = w_prof * (1 - proficiency_score)   # low mastery -> study more
         + w_prio * (priority / 5.0)          # exam importance 1..5, normalized
         + w_dead * deadline_pressure         # near/weighted due dates

Every scored topic carries human-readable reasons ("weak mastery 0.31",
"exam 'CAT-2' in 6d") so plans are trusted, not just followed. Topics with
no Proficiency row are treated as score=0.0 (weakest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ._helpers import get_or_404


@dataclass
class TopicScore:
    topic: models.Topic
    need: float
    reasons: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)


class ScheduleService:
    @staticmethod
    def deadline_pressure_by_topic(
        db: Session, user_id: int, now: datetime
    ) -> tuple[dict[int, float], dict[int, list[models.Deadline]]]:
        """Pressure per topic + the live deadlines behind it (for reasons)."""
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

        cap = settings.scheduler.deadline_cap
        pressure: dict[int, float] = {}
        drivers: dict[int, list[models.Deadline]] = {}
        for dl in deadlines:
            if days_left[dl.id] <= 0.0:
                continue
            p = dl.weight * cap / days_left[dl.id]
            if dl.topic_id is not None:
                pressure[dl.topic_id] = pressure.get(dl.topic_id, 0.0) + p
                drivers.setdefault(dl.topic_id, []).append(dl)
            else:
                for tid, cid in topic_course.items():
                    if cid == dl.course_id:
                        pressure[tid] = pressure.get(tid, 0.0) + p
                        drivers.setdefault(tid, []).append(dl)
        return pressure, drivers

    @staticmethod
    def score_topics(db: Session, user_id: int, now: datetime) -> list[TopicScore]:
        """Score every schedulable topic by study need, highest first.

        Each item carries human-readable reasons so plans explain themselves.
        """
        cfg = settings.scheduler
        pressure, drivers = ScheduleService.deadline_pressure_by_topic(db, user_id, now)
        profs = db.scalars(
            select(models.Proficiency).where(models.Proficiency.user_id == user_id)
        ).all()
        prof_by_topic = {p.topic_id: p.score for p in profs}

        scored: list[TopicScore] = []
        for topic in db.scalars(select(models.Topic)).all():
            if topic.module is None:
                continue  # only topics linked to a course are schedulable
            mastery = prof_by_topic.get(topic.id)
            mastery_part = cfg.w_prof * (1.0 - (mastery if mastery is not None else 0.0))
            prio_part = cfg.w_prio * (topic.priority / 5.0)
            dead_part = cfg.w_dead * pressure.get(topic.id, 0.0)
            need = mastery_part + prio_part + dead_part

            reasons: list[str] = []
            if mastery is None:
                reasons.append("not yet attempted")
            elif mastery < 0.5:
                reasons.append(f"weak mastery {mastery:.2f}")
            else:
                reasons.append(f"solid mastery {mastery:.2f}")
            if topic.priority >= 4:
                reasons.append(f"high exam priority {topic.priority}/5")
            for dl in drivers.get(topic.id, [])[:2]:
                days = max((dl.due_date - now).days, 1)
                reasons.append(f"exam '{dl.title}' in {days}d")
            scored.append(TopicScore(
                topic=topic,
                need=round(need, 4),
                reasons=reasons,
                components={
                    "mastery": round(mastery_part, 4),
                    "priority": round(prio_part, 4),
                    "deadline": round(dead_part, 4),
                },
            ))
        scored.sort(key=lambda s: s.need, reverse=True)
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
        for item in scored:
            if not free_slots:
                break
            slot = free_slots.pop(0)
            plan = models.Plan(
                user_id=user_id,
                slot_id=slot.id,
                topic_id=item.topic.id,
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
