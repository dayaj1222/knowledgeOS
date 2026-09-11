"""Ingest pipeline: upload → extract → chunk → tag.

Kept as a separate module (not a router file) because extraction, chunking,
and tagging are a distinct subsystem that grows independently of the HTTP
layer. Passages are routed to topics deterministically (term scoring on
topic names + descriptions) — no LLM, no vector index.
"""

from .chunker import chunk_text, strip_boilerplate
from .extractor import extract_text
from .storage import save_upload
from .tagger import assign_passages

__all__ = ["extract_text", "chunk_text", "strip_boilerplate", "assign_passages", "save_upload"]
