"""Baseline: SM-2 step math. Locks current behavior — change deliberately."""

from app.services.review_service import score_to_quality, sm2_step


def test_first_success_starts_interval_at_1():
    interval, ease = sm2_step(5, 0, 2.5)
    assert interval == 1
    assert ease > 2.5  # perfect recall raises ease


def test_good_but_imperfect_leaves_ease_flat():
    _, ease = sm2_step(4, 0, 2.5)
    assert ease == 2.5  # SM-2: quality 4 is ease-neutral by formula


def test_second_success_jumps_to_6():
    interval, _ = sm2_step(4, 1, 2.5)
    assert interval == 6


def test_failure_resets_interval_and_drops_ease():
    interval, ease = sm2_step(2, 10, 2.5)
    assert interval == 1
    assert ease < 2.5


def test_ease_never_below_floor():
    _, ease = sm2_step(0, 30, 1.35)
    assert ease >= 1.3


def test_score_to_quality_mapping():
    assert score_to_quality(0.0) == 0
    assert score_to_quality(0.85) == 4
    assert score_to_quality(1.0) == 5
    assert score_to_quality(1.5) == 5  # clamped, not exploded
