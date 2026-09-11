"""Baseline: in-chat understanding math (the 0.85-that-ate-a-topic bug class).

Locks the CURRENT contract:
- fresh topic  -> score = demonstrated * coverage  (fair slice credit)
- existing     -> damped nudge, scaled by coverage (never jumps)
- omitted coverage defaults to 0.2, never 1.0
- SM-2 untouched below coverage 0.5
"""

from datetime import datetime

from app import models
from app.agent.tutor_tools import DEFAULT_COVERAGE, REVIEW_MIN_COVERAGE, record_understanding


class FakeDB:
    """Minimal stand-in: real Proficiency/Review rows, no database."""

    def __init__(self, prof=None):
        self.prof = prof
        self.events = []
        self.review = models.Review(
            user_id=1, topic_id=1, due_date=datetime.now(),
            interval_days=0, ease_factor=2.5,
        )
        self.review_touched = False

    def get(self, model, _id):
        return object()  # topic exists

    def scalar(self, q):
        if "reviews" in str(q):
            return self.review
        return self.prof

    def add(self, o):
        if isinstance(o, models.Proficiency):
            self.prof = o
        elif isinstance(o, models.ProficiencyEvent):
            self.events.append(o)
        elif isinstance(o, models.Review):
            self.review_touched = True

    def commit(self):
        pass


def test_defaults_are_conservative():
    assert DEFAULT_COVERAGE == 0.2
    assert REVIEW_MIN_COVERAGE == 0.5


def test_fresh_topic_gets_slice_credit_not_full_score():
    db = FakeDB()
    r = record_understanding(db, 1, {"topic_id": 1, "demonstrated": 0.85, "coverage": 0.15})
    assert r["score"] == 0.13  # 0.85*0.15 = 0.1275, NOT 0.85
    assert r["observed"] == 0.13
    assert r["sm2_updated"] is False
    # ledger answers "why is my score X?"
    assert len(db.events) == 1
    e = db.events[0]
    assert (e.source, e.old_score, e.new_score) == ("chat_understanding", 0.0, 0.1275)


def test_omitted_coverage_defaults_low():
    r = record_understanding(FakeDB(), 1, {"topic_id": 1, "demonstrated": 0.85})
    assert r["coverage"] == 0.2
    assert r["score"] == 0.17


def test_existing_topic_nudges_instead_of_jumping():
    db = FakeDB(models.Proficiency(user_id=1, topic_id=1, score=0.4))
    r = record_understanding(db, 1, {"topic_id": 1, "demonstrated": 0.9, "coverage": 0.8})
    assert r["score"] == 0.48  # 0.84*0.4 + 0.16*0.9
    assert r["sm2_updated"] is True


def test_small_slice_leaves_schedule_alone():
    db = FakeDB(models.Proficiency(user_id=1, topic_id=1, score=0.4))
    r = record_understanding(db, 1, {"topic_id": 1, "demonstrated": 0.9, "coverage": 0.2})
    assert r["sm2_updated"] is False
    assert db.review_touched is False


def test_bad_input_is_an_error_dict_not_an_exception():
    assert "error" in record_understanding(FakeDB(), 1, {"demonstrated": 0.5})
    assert "error" in record_understanding(FakeDB(), 1, {"topic_id": 1, "demonstrated": 0.5, "coverage": 0})
