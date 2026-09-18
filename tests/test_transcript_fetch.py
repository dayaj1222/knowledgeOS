"""Transcript fetching handles non-English and generated caption tracks."""

from types import SimpleNamespace

from app.agent import web


def test_fetch_transcript_selects_best_available_caption_track(monkeypatch):
    class Fetched(list):
        language_code = "en"
        language = "English"

    class Track:
        def __init__(self, code, generated, text):
            self.language_code = code
            self.is_generated = generated
            self._text = text

        def fetch(self):
            return Fetched([SimpleNamespace(text=self._text, start=42.5)])

    class FakeApi:
        def list(self, _video_id):
            return [Track("hi", True, "नमस्ते"), Track("en", False, "priority ceiling")]

    monkeypatch.setitem(__import__("sys").modules, "youtube_transcript_api",
                        SimpleNamespace(YouTubeTranscriptApi=FakeApi))

    result = web.fetch_transcript("video123")

    assert result["language"] == "en"
    assert result["full_text"] == "priority ceiling"
    assert result["segments"] == [{"start": 42.5, "text": "priority ceiling"}]


def test_select_transcript_moment_returns_best_caption_window():
    moment = web.select_transcript_moment([
        {"start": 10, "text": "First, here is a quick introduction."},
        {"start": 83, "text": "A SQL join combines rows between tables using a matching key."},
        {"start": 91, "text": "Use an inner join when both tables need a matching row."},
    ], "explain SQL inner join", "SQL joins combine related tables")

    assert moment is not None
    assert moment["start_seconds"] == 83
    assert moment["timestamp_label"] == "1:23"
