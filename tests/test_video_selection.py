"""Video cards show one transcript-ranked result and rotate on request."""

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import ai, models
from app.agent import tutor_tools


def _db():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        models.User(id=1, name="Student", email="student@example.test"),
        models.Course(id=2, user_id=1, name="Course", code="C"),
        models.Module(id=3, course_id=2, name="Module"),
        models.Topic(id=4, module_id=3, name="Priority ceiling"),
        models.Conversation(id=5, user_id=1, title="Tutor"),
    ])
    db.commit()
    return db


def test_video_tool_returns_next_unseen_transcript_ranked_candidate(monkeypatch):
    db = _db()
    monkeypatch.setattr(tutor_tools, "_search_videos", lambda *_: {"videos": [
        {"video_id": "weak", "title": "Weak"},
        {"video_id": "best", "title": "Best"},
        {"video_id": "middle", "title": "Middle"},
    ]})
    scores = {"weak": 0.1, "best": 0.9, "middle": 0.5}
    monkeypatch.setattr(tutor_tools, "_fetch_transcript", lambda video_id: {
        "full_text": video_id,
    })
    monkeypatch.setattr(tutor_tools, "_score_relevance", lambda transcript, *_: {
        "relevance": scores[transcript], "matched": [transcript],
    })
    monkeypatch.setattr(tutor_tools, "_hybrid_caption_candidates", lambda *_: [])
    monkeypatch.setattr("app.services.retrieval.grounding_for_topic", lambda *_: ["ceiling"])
    token = tutor_tools.current_conversation.set(5)
    try:
        first = asyncio.run(tutor_tools.find_videos(db, 1, {"query": "ceiling", "topic_id": 4}))
        db.add(models.Card(conversation_id=5, kind="video", payload={"videos": first["videos"]}))
        db.commit()
        second = asyncio.run(tutor_tools.find_videos(db, 1, {"query": "ceiling", "topic_id": 4}))
    finally:
        tutor_tools.current_conversation.reset(token)

    assert first["videos"] == [first["videos"][0]]
    assert first["videos"][0]["video_id"] == "best"
    assert second["videos"][0]["video_id"] == "middle"


def test_video_tool_supports_external_study_without_topic(monkeypatch):
    monkeypatch.setattr(tutor_tools, "_search_videos", lambda *_: {"videos": [
        {"video_id": "dsa", "title": "DSA"},
    ]})
    monkeypatch.setattr(tutor_tools, "_fetch_transcript", lambda _: {
        "full_text": "binary search finds a target in a sorted array",
        "segments": [{"start": 42, "text": "binary search finds a target in a sorted array"}],
    })
    monkeypatch.setattr(tutor_tools, "_hybrid_caption_candidates", lambda *_: [])

    result = asyncio.run(tutor_tools.find_videos(_db(), 1, {
        "query": "binary search data structures algorithms", "focus": "binary search",
    }))

    assert result["videos"][0]["video_id"] == "dsa"
    assert result["videos"][0]["external"] is True


def test_video_tool_falls_back_when_topic_id_does_not_match_requested_concept(monkeypatch):
    db = _db()  # Topic 4 is "Priority ceiling", not binary search.
    monkeypatch.setattr(tutor_tools, "_search_videos", lambda *_: {"videos": [
        {"video_id": "dsa", "title": "Binary search"},
    ]})
    monkeypatch.setattr(tutor_tools, "_fetch_transcript", lambda _: {
        "full_text": "binary search finds a target in a sorted array",
        "segments": [{"start": 42, "text": "binary search finds a target in a sorted array"}],
    })
    monkeypatch.setattr(tutor_tools, "_hybrid_caption_candidates", lambda *_: [{
        "start_seconds": 42,
        "timestamp_label": "0:42",
        "timestamp_excerpt": "binary search finds a target",
    }])

    async def choose(*_args):
        return {"start_seconds": 42, "seek_confidence": "high"}

    monkeypatch.setattr("app.ai.choose_video_moment", choose)

    result = asyncio.run(tutor_tools.find_videos(db, 1, {
        "query": "binary search data structures", "topic_id": 4,
    }))

    assert result["videos"][0]["video_id"] == "dsa"
    assert result["videos"][0]["external"] is True
    assert result["videos"][0]["start_seconds"] == 42


def test_video_tool_seeks_to_llm_reranked_hybrid_caption(monkeypatch):
    db = _db()
    monkeypatch.setattr(tutor_tools, "_search_videos", lambda *_: {"videos": [
        {"video_id": "best", "title": "Best"},
    ]})
    monkeypatch.setattr(tutor_tools, "_fetch_transcript", lambda _: {
        "full_text": "priority ceiling", "segments": [{"start": 70, "text": "ceiling"}],
    })
    monkeypatch.setattr(tutor_tools, "_score_relevance", lambda *_: {
        "relevance": 0.9, "matched": ["ceiling"],
    })
    monkeypatch.setattr(tutor_tools, "_hybrid_caption_candidates", lambda *_: [
        {"start_seconds": 70, "timestamp_label": "1:10", "timestamp_excerpt": "ceiling", "retrieval_score": 0.03},
        {"start_seconds": 140, "timestamp_label": "2:20", "timestamp_excerpt": "protocol", "retrieval_score": 0.02},
    ])
    monkeypatch.setattr("app.services.retrieval.grounding_for_topic", lambda *_: ["ceiling"])

    async def choose(*_args):
        return {"start_seconds": 70, "seek_confidence": "high"}

    monkeypatch.setattr(ai, "choose_video_moment", choose)
    out = asyncio.run(tutor_tools.find_videos(db, 1, {
        "query": "priority ceiling", "topic_id": 4,
        "focus": "Why the ceiling prevents priority inversion",
        "technical_terms": ["priority inversion", "ceiling"],
    }))

    video = out["videos"][0]
    assert video["start_seconds"] == 70
    assert video["timestamp_label"] == "1:10"
    assert video["seek_confidence"] == "high"
