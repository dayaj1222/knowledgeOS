"""Save uploaded bytes to disk with a sanitized name, atomically.

Files live at storage/uploads/<resource_id>/<name>. The DB stores only the
relative path; the raw bytes are never trusted from the client beyond the
multipart body.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # project root
STORAGE_DIR = ROOT / "storage"

MAX_SIZE = 50 * 1024 * 1024  # 50 MB


def _sanitize(name: str) -> str:
    # strip path separators and anything that isn't a word, dot, dash, or space
    cleaned = re.sub(r"[^\w.\- ]+", "_", name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "upload"


def save_upload(resource_id: int, filename: str, data: bytes) -> str:
    """Write the file bytes and return the stored RELATIVE path (from ROOT).

    Atomic: writes to a temp file then renames, so a failed upload never leaves
    a half-written file behind. Raises ValueError if over MAX_SIZE.
    """
    if len(data) > MAX_SIZE:
        raise ValueError("file exceeds 50 MB limit")
    safe = _sanitize(filename)
    dir_path = STORAGE_DIR / "uploads" / str(resource_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    dest = dir_path / safe
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.rename(dest)
    return str(dest.relative_to(ROOT))
