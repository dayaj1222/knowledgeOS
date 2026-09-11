"""Baseline: transcript-vs-topic relevance scoring (video verification)."""

from app.agent.web import _keywords, score_relevance

TRANSCRIPT = (
    "Today we cover the priority ceiling protocol for shared resources. "
    "When a high priority task blocks on a resource held by a low task, "
    "the holder inherits the ceiling priority to avoid unbounded blocking."
)
TOPIC_TEXT = (
    "Shared Resources priority inversion ceiling protocol resource holder "
    "blocking critical section high low task"
)


def test_on_topic_scores_high():
    s = score_relevance(TRANSCRIPT, TOPIC_TEXT, "Shared Resources")
    assert s["relevance"] >= 0.3
    assert "resources" in s["matched"]


def test_off_topic_scores_zero():
    s = score_relevance(
        "Baking sourdough bread needs flour water salt and a hot oven.",
        TOPIC_TEXT,
        "Shared Resources",
    )
    assert s["relevance"] == 0.0
    assert s["matched"] == []


def test_empty_topic_text_scores_zero():
    assert score_relevance(TRANSCRIPT, "", "")["relevance"] == 0.0


def test_stopwords_dont_count_as_matches():
    keys = _keywords("the and every full but priority ceiling")
    assert "priority" in keys and "ceiling" in keys
    assert "the" not in keys and "every" not in keys and "but" not in keys
