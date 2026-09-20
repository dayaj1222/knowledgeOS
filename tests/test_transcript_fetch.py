"""Transcript fetching handles non-English and generated caption tracks."""

import sys
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


def test_hybrid_caption_candidates_return_semantic_and_lexical_matches(monkeypatch):
    monkeypatch.setattr(web, "_keywords", lambda text: set(text.lower().split()))
    monkeypatch.setitem(sys.modules, "app.ingest.embeddings", None)
    candidates = web.hybrid_caption_candidates([
        {"start": 10, "text": "First, here is a quick introduction."},
        {"start": 83, "text": "A SQL join combines rows between tables using a matching key."},
        {"start": 91, "text": "Use an inner join when both tables need a matching row."},
    ], "SQL inner join", "SQL joins", ["Inner joins require a matching key."], top=2)

    assert candidates
    assert [candidate["start_seconds"] for candidate in candidates] == [83, 91]
    assert candidates[0]["timestamp_label"] == "1:23"


def test_hybrid_caption_candidates_caps_dense_embedding_batch(monkeypatch):
    calls = []

    class Embeddings:
        @staticmethod
        def embed_texts(texts):
            calls.append(texts)
            return [__import__("numpy").ones(2) for _ in texts]

    monkeypatch.setitem(sys.modules, "app.ingest.embeddings", Embeddings)
    web.hybrid_caption_candidates(
        [{"start": i, "text": f"binary search step {i}"} for i in range(400)],
        "binary search", "", [], top=1,
    )

    assert len(calls) == 1
    assert len(calls[0]) <= web.CAPTION_DENSE_CANDIDATES + 1
