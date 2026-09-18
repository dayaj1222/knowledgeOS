"""Video cards show one transcript-ranked result and rotate on request."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
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
    monkeypatch.setattr("app.services.retrieval.grounding_for_topic", lambda *_: ["ceiling"])
    token = tutor_tools.current_conversation.set(5)
    try:
        first = tutor_tools.find_videos(db, 1, {"query": "ceiling", "topic_id": 4})
        db.add(models.Card(conversation_id=5, kind="video", payload={"videos": first["videos"]}))
        db.commit()
        second = tutor_tools.find_videos(db, 1, {"query": "ceiling", "topic_id": 4})
    finally:
        tutor_tools.current_conversation.reset(token)

    assert first["videos"] == [first["videos"][0]]
    assert first["videos"][0]["video_id"] == "best"
    assert second["videos"][0]["video_id"] == "middle"


def test_video_tool_requires_topic_for_caption_verification():
    result = tutor_tools.find_videos(_db(), 1, {"query": "ceiling"})

    assert result["videos"] == []
    assert "topic_id is required" in result["error"]
