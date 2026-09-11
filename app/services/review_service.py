"""Spaced repetition service: SM-2 scheduling on the Review table.

STRICT CONTRACT (the mastery/retrieval split): this table tracks RETRIEVAL
strength only — when to surface a topic for recall. It is fed exclusively
by genuine recall events: graded quiz attempts ("quiz"), review-card
self-ratings ("review"), and study sessions ("study"). Chat-demonstrated
understanding ("chat") counts only for substantial slices (the tutor gates
it); it never drives the schedule alone. Mastery scores live in Proficiency
+ its ledger — the two systems correlate but must not conflate.

Quality mapping: quality = round(score_or_confidence * 5).

SM-2 update (SuperMemo-2):
  - quality < 3 → re-learn: interval resets to 1 day
  - otherwise interval grows 1 → 6 → interval * ease_factor
  - ease_factor drifts with performance, floored at 1.3

The frontend's "due queue" (GET /users/{id}/reviews/due) is simply reviews
with due_date <= now, oldest first — so the learner always sees what to
revisit today, and completing it (quiz or study log) pushes it forward.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models

MIN_EASE = 1.3


def sm2_step(quality: int, interval_days: int, ease_factor: float) -> tuple[int, float]:
    """One SM-2 update. Returns (new_interval_days, new_ease_factor)."""
    quality = max(0, min(5, quality))
    if quality < 3:
        new_interval = 1
    elif interval_days <= 0:
        new_interval = 1
    elif interval_days == 1:
        new_interval = 6
    else:
        new_interval = round(interval_days * ease_factor)
    new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return new_interval, round(max(MIN_EASE, new_ease), 2)


def score_to_quality(score: float) -> int:
    """Map a 0.0-1.0 score/confidence to SM-2 quality 0-5."""
    return max(0, min(5, round(score * 5)))


class ReviewService:
    @staticmethod
    def get_or_create(db: Session, user_id: int, topic_id: int) -> models.Review:
        review = db.scalar(
            select(models.Review)
            .where(
                models.Review.user_id == user_id,
                models.Review.topic_id == topic_id,
            )
            .order_by(models.Review.id.desc())
        )
        if review is None:
            review = models.Review(
                user_id=user_id,
                topic_id=topic_id,
                due_date=datetime.now(),
                interval_days=0,
                ease_factor=2.5,
            )
            db.add(review)
        return review

    @staticmethod
    def record_result(
        db: Session, *, user_id: int, topic_id: int, quality: int,
        source: str = "quiz",
        now: datetime | None = None,
    ) -> models.Review:
        """Fold one recall result into the topic's SM-2 schedule (no commit).

        source ∈ quiz | review | study | chat — stamped on last_source so the
        schedule's driver is always auditable (see module contract).
        """
        now = now or datetime.now()
        review = ReviewService.get_or_create(db, user_id, topic_id)
        interval, ease = sm2_step(quality, review.interval_days, review.ease_factor)
        review.interval_days = interval
        review.ease_factor = ease
        review.due_date = now + timedelta(days=interval)
        review.last_source = source
        db.add(review)
        return review

    @staticmethod
    def due_queue(
        db: Session, user_id: int, limit: int = 20, now: datetime | None = None
    ) -> list[dict]:
        """Reviews due now or overdue, oldest first, with topic context."""
        now = now or datetime.now()
        rows = db.scalars(
            select(models.Review)
            .where(models.Review.user_id == user_id, models.Review.due_date <= now)
            .order_by(models.Review.due_date)
            .limit(limit)
        ).all()
        out = []
        for r in rows:
            topic = db.get(models.Topic, r.topic_id)
            out.append(
                {
                    "topic_id": r.topic_id,
                    "topic_name": topic.name if topic else f"Topic #{r.topic_id}",
                    "due_date": r.due_date.isoformat(),
                    "interval_days": r.interval_days,
                    "ease_factor": r.ease_factor,
                    "overdue_days": max((now - r.due_date).days, 0),
                }
            )
        return out
