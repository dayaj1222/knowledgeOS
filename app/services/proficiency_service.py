"""Proficiency: the ONLY writer of mastery scores, and its ledger.

Every score change flows through ProficiencyService.record — fresh topics
start at the observed value, existing ones move old + alpha*(observed-old) —
and every change appends a ProficiencyEvent (source, old → new, evidence).
"Why is my score X?" is answered by reading the ledger, never by autopsy.

Retrieval scheduling (SM-2 Review rows) is a separate system fed only by
recall events; it never reads this table and this service never writes it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models

# Sources — the complete set of writers. Add one here, not inline elsewhere.
QUIZ_ATTEMPT = "quiz_attempt"
CHAT_UNDERSTANDING = "chat_understanding"
STUDY_LOG = "study_log"
MANUAL_OVERRIDE = "manual_override"


class ProficiencyService:
    @staticmethod
    def record(
        db: Session,
        *,
        user_id: int,
        topic_id: int,
        observed: float,
        alpha: float,
        source: str,
        ref_id: int | None = None,
        evidence: str | None = None,
        fresh_value: float | None = None,
    ) -> tuple[models.Proficiency, models.ProficiencyEvent]:
        """Blend one observation into mastery. No commit (callers own it).

        Existing rows move old + alpha*(observed-old). Fresh rows start at
        fresh_value (defaults to observed) — e.g. chat credit starts at
        demonstrated*coverage while later nudges target demonstrated.
        """
        observed = max(0.0, min(1.0, observed))
        alpha = max(0.0, min(1.0, alpha))
        prof = db.scalar(
            select(models.Proficiency).where(
                models.Proficiency.user_id == user_id,
                models.Proficiency.topic_id == topic_id,
            )
        )
        if prof is None:
            start = observed if fresh_value is None else fresh_value
            old, new = 0.0, round(max(0.0, min(1.0, start)), 4)
            prof = models.Proficiency(user_id=user_id, topic_id=topic_id, score=new)
            db.add(prof)
        else:
            old = prof.score
            new = round((1 - alpha) * old + alpha * observed, 4)
            prof.score = new
            db.add(prof)
        event = models.ProficiencyEvent(
            user_id=user_id,
            topic_id=topic_id,
            source=source,
            old_score=round(old, 4),
            new_score=new,
            observed=round(observed, 4),
            alpha=round(alpha, 4),
            ref_id=ref_id,
            evidence=(evidence or "")[:300] or None,
        )
        db.add(event)
        return prof, event

    @staticmethod
    def history(
        db: Session, *, user_id: int, topic_id: int, limit: int = 20
    ) -> list[models.ProficiencyEvent]:
        return list(
            db.scalars(
                select(models.ProficiencyEvent)
                .where(
                    models.ProficiencyEvent.user_id == user_id,
                    models.ProficiencyEvent.topic_id == topic_id,
                )
                .order_by(models.ProficiencyEvent.id.desc())
                .limit(limit)
            ).all()
        )
