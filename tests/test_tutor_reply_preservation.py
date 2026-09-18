"""Regression coverage for prose emitted alongside silent agent tools."""

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.agent import tutor
from app.models import Base


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(models.User(id=1, name="Student", email="student@example.test"))
    db.add(models.Conversation(id=1, user_id=1, title="Tutor"))
    db.commit()
    return db


def test_silent_tool_cannot_erase_explanation(monkeypatch):
    """Providers can return text + a tool call, then an empty final message."""
    db = _db()
    responses = iter([
        {
            "content": "The stack is last-in, first-out.",
            "tool_calls": [{"id": "call-1", "function": {
                "name": "record_understanding", "arguments": '{"topic_id": 1}'
            }}],
        },
        {"content": "", "tool_calls": []},
    ])

    async def fake_chat(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(tutor, "chat_with_tools", fake_chat)
    monkeypatch.setattr(tutor, "openai_tools", lambda: [])
    monkeypatch.setattr(tutor, "run_tool", lambda *_args: {"recorded": True})

    out = tutor._run_tool_loop(db, 1, 1, [{"role": "user", "content": "Explain stacks"}])

    assert out["reply"] == "The stack is last-in, first-out."
    assert out["tool_calls"] == [{
        "tool": "record_understanding", "args": {"topic_id": 1},
        "result_preview": '{"recorded": true}',
    }]


def test_streaming_silent_tool_cannot_erase_explanation(monkeypatch):
    db = _db()
    calls = iter([True, False])

    async def fake_stream(*_args, **_kwargs):
        if next(calls):
            yield "token", "A queue is first-in, first-out."
            yield "done", {
                "content": "A queue is first-in, first-out.",
                "tool_calls": [{"id": "call-1", "function": {
                    "name": "record_understanding", "arguments": '{"topic_id": 1}'
                }}],
            }
        else:
            yield "done", {"content": "", "tool_calls": []}

    monkeypatch.setattr(tutor, "chat_stream", fake_stream)
    monkeypatch.setattr(tutor, "openai_tools", lambda: [])
    monkeypatch.setattr(tutor, "run_tool", lambda *_args: {"recorded": True})

    async def collect():
        return [event async for event in tutor.stream_tutor_turn(db, 1, 1, "Explain queues")]

    events = asyncio.run(collect())
    assert events[-1]["reply"] == "A queue is first-in, first-out."
