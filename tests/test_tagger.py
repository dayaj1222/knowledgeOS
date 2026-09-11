"""Deterministic tagger: vocabulary scoring, no LLM.

Locks: clear topics assign high, boilerplate stays untagged (never
force-filed), near-ties surface as extras, plurals stem.
"""

from app.ingest.tagger import (
    ASSIGN_THRESHOLD,
    EXTRA_THRESHOLD,
    assign_passages,
    score_chunk,
    topic_terms,
)

TOPICS = [
    {
        "id": 1,
        "name": "Shared Resources",
        "description": "Mutual exclusion for shared resources; critical sections must be protected.",
    },
    {
        "id": 2,
        "name": "Priority Inversion",
        "description": "A low priority task blocks a high priority task by holding a resource.",
    },
    {
        "id": 3,
        "name": "Deadlocks",
        "description": "Circular wait: mutual exclusion, hold and wait, no preemption.",
    },
]


def test_clear_chunk_assigns_high():
    out = assign_passages(
        [{
            "id": 1,
            "content": "# Priority Inversion\n\nA low priority task holding a lock blocks the high task.",
            "section_path": "Priority Inversion",
        }],
        TOPICS,
    )
    assert out[1]["primary"] == 2
    assert out[1]["confidence"] >= 0.5


def test_boilerplate_stays_untagged():
    out = assign_passages(
        [{"id": 2, "content": "Module 3 Dept of CSE", "section_path": ""}],
        TOPICS,
    )
    assert out[2]["primary"] is None
    assert out[2]["confidence"] == 0.0


def test_empty_inputs():
    assert assign_passages([], TOPICS) == {}
    out = assign_passages([{"id": 1, "content": "text", "section_path": ""}], [])
    assert out[1]["primary"] is None


def test_plurals_stem():
    # "resources" in text must match topic term "resource" and vice versa
    score, matched = score_chunk(
        "resources are shared", "", topic_terms("Shared Resource", "")
    )
    assert score >= ASSIGN_THRESHOLD
    assert "resource" in matched


def test_section_naming_boosts():
    plain, _ = score_chunk("generic waiting text here", "", topic_terms("Deadlocks", "circular wait"))
    named, _ = score_chunk(
        "generic waiting text here", "Deadlocks", topic_terms("Deadlocks", "circular wait")
    )
    assert named > plain


def test_thresholds_sane():
    assert 0.0 < ASSIGN_THRESHOLD < EXTRA_THRESHOLD < 1.0
