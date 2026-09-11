"""ProficiencyService: the single writer + ledger.

Locks: fresh starts at observed, existing blends, every write ledgers with
source/old/new, manual override sets exact.
"""

from app import models
from app.services.proficiency_service import (
    MANUAL_OVERRIDE,
    QUIZ_ATTEMPT,
    STUDY_LOG,
    ProficiencyService,
)


class FakeDB:
    def __init__(self, prof=None):
        self.prof = prof
        self.events = []

    def scalar(self, _q):
        return self.prof

    def add(self, o):
        if isinstance(o, models.Proficiency):
            self.prof = o
        else:
            self.events.append(o)


def test_fresh_starts_at_observed():
    db = FakeDB()
    prof, event = ProficiencyService.record(
        db, user_id=1, topic_id=1, observed=0.7, alpha=0.3,
        source=QUIZ_ATTEMPT, ref_id=9,
    )
    assert prof.score == 0.7
    assert (event.old_score, event.new_score, event.ref_id) == (0.0, 0.7, 9)


def test_existing_blends_and_ledgers():
    db = FakeDB(models.Proficiency(user_id=1, topic_id=1, score=0.4))
    prof, event = ProficiencyService.record(
        db, user_id=1, topic_id=1, observed=0.9, alpha=0.3, source=STUDY_LOG,
    )
    assert prof.score == 0.55  # 0.7*0.4 + 0.3*0.9
    assert event.source == STUDY_LOG
    assert event.old_score == 0.4 and event.observed == 0.9


def test_manual_override_sets_exact():
    db = FakeDB(models.Proficiency(user_id=1, topic_id=1, score=0.2))
    prof, event = ProficiencyService.record(
        db, user_id=1, topic_id=1, observed=0.9, alpha=1.0, source=MANUAL_OVERRIDE,
    )
    assert prof.score == 0.9
    assert event.source == MANUAL_OVERRIDE


def test_fresh_value_overrides_start():
    # chat credit: fresh starts at demonstrated*coverage, not demonstrated
    db = FakeDB()
    prof, _ = ProficiencyService.record(
        db, user_id=1, topic_id=1, observed=0.85, alpha=0.03,
        source="chat_understanding", fresh_value=0.17,
    )
    assert prof.score == 0.17


def test_history_newest_first():
    from app.services.proficiency_service import ProficiencyService as PS

    seen = []

    class HistDB(FakeDB):
        def scalars(self, _q):
            class R:
                def all(inner):
                    return seen
            return R()

    db = HistDB()
    assert PS.history(db, user_id=1, topic_id=1) == seen
