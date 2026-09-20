"""Chat image paste: multipart assembly for the LLM, text-only history.

Contract: the turn's user message goes out as OpenAI multipart
(text + first image_url); the persisted row stays text with a marker;
no images → plain string content as before.
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import ai, models
from app.agent import tutor
from app.database import Base


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(models.User(id=1, name="t", email="t@t.t"))
        s.commit()
        yield s


def test_image_turn_builds_multipart(db, monkeypatch):
    monkeypatch.setattr(tutor, "persist_chat_image", lambda cid, _: f"/storage/chat-images/chat-{cid}-test.jpg")
    cid, messages, _ = tutor._open_turn(
        db, 1, None, "what is this?", None, ["data:image/jpeg;base64,AAA"])
    user_msg = messages[-1]
    assert user_msg["role"] == "user"
    parts = user_msg["content"]
    assert isinstance(parts, list)
    assert parts[0]["type"] == "text" and "what is this?" in parts[0]["text"]
    assert parts[1] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAA"}}
    row = db.query(models.ChatMessage).filter_by(conversation_id=cid).one()
    assert row.content == "what is this?"
    assert row.images == [f"/storage/chat-images/chat-{cid}-test.jpg"]


def test_text_only_turn_unchanged(db):
    cid, messages, _ = tutor._open_turn(db, 1, None, "plain question", None, None)
    assert isinstance(messages[-1]["content"], str)
    row = db.query(models.ChatMessage).filter_by(conversation_id=cid).one()
    assert row.content == "plain question"


def test_reply_target_is_hidden_context_not_persisted_message(db):
    cid, messages, _ = tutor._open_turn(
        db,
        1,
        None,
        "What method are we using?",
        {"reply_target": {"source": "tutor", "text": "Expected counts are built from margins."}},
    )
    row = db.query(models.ChatMessage).filter_by(conversation_id=cid).one()
    assert row.content == "What method are we using?"
    content = messages[-1]["content"]
    assert "[REPLY TARGET]" in content
    assert "Expected counts are built from margins." in content


def test_streaming_image_turn_uses_multimodal_completion(monkeypatch):
    seen = {}

    async def fake_chat_with_tools(messages, **kwargs):
        seen["messages"] = messages
        seen["kwargs"] = kwargs
        return {"content": "I can see the image.", "tool_calls": []}

    monkeypatch.setattr(ai, "chat_with_tools", fake_chat_with_tools)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What is shown?"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAA"}},
        ],
    }]

    async def collect():
        return [event async for event in ai.chat_stream(messages, thread_id="chat-1")]

    events = asyncio.run(collect())

    assert seen["messages"] == messages
    assert seen["kwargs"]["thread_id"] == "chat-1"
    assert events == [
        ("token", "I can see the image."),
        ("done", {"content": "I can see the image.", "tool_calls": []}),
    ]
