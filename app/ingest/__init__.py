"""Ingest pipeline: upload → extract → chunk → store.

Kept as a separate module (not a router file) because extraction, chunking,
and storage are a distinct subsystem that grows (OCR, semantic boundaries)
independently of the HTTP layer. Passages are routed to topics by topic_id
(plain SQL) — no vector index.
"""

from .extractor import extract_text
from .chunker import chunk_text
from .storage import save_upload

__all__ = ["extract_text", "chunk_text", "save_upload"]
