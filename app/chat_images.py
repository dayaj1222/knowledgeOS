"""Durable local storage for chat image attachments."""

from __future__ import annotations

import base64
import binascii
import re
from uuid import uuid4

from .ingest.storage import STORAGE_DIR

_DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")
_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_CHAT_IMAGE_BYTES = 8 * 1024 * 1024


def persist_chat_image(conversation_id: int, data_url: str) -> str:
    """Write one browser data URL and return its public local URL."""
    match = _DATA_URL.fullmatch((data_url or "").strip())
    if match is None:
        raise ValueError("chat image must be a JPEG, PNG, or WebP data URL")
    mime, encoded = match.groups()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("chat image has invalid base64 data") from exc
    if not raw or len(raw) > MAX_CHAT_IMAGE_BYTES:
        raise ValueError("chat image must be between 1 byte and 8 MB")
    directory = STORAGE_DIR / "chat-images"
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"chat-{conversation_id}-{uuid4().hex}{_EXTENSIONS[mime]}"
    destination = directory / filename
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(destination)
    return f"/storage/chat-images/{filename}"
