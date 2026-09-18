"""Local vector embeddings for module-pool RAG (no API, no cost).

Model: BAAI/bge-small-en-v1.5 via fastembed (ONNX, 384-dim). Weights
download once (~100MB) on first use; thereafter fully offline.
The model loads lazily — importing this module never blocks startup.

Storage: float32 bytes in passage_embeddings.vec; cosine ranked with
numpy inside one module pool (hundreds of rows — microseconds).
"""

from __future__ import annotations

import threading

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384

_lock = threading.Lock()
_model = None


def _load():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding

                _model = TextEmbedding(MODEL_NAME)
    return _model


def is_available() -> bool:
    """True when the model loads (weights cached/downloadable)."""
    try:
        _load()
        return True
    except Exception:
        return False


def embed_texts(texts: list[str]) -> list[np.ndarray]:
    """Embed a batch; returns L2-normalized float32 vectors."""
    if not texts:
        return []
    vecs = list(_load().embed(texts))
    out = []
    for v in vecs:
        a = np.asarray(v, dtype=np.float32)
        n = float(np.linalg.norm(a))
        out.append(a / n if n > 0 else a)
    return out


def pack(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def rank(query_vec: np.ndarray, rows: list[tuple[int, bytes]], top: int) -> list[tuple[int, float]]:
    """Cosine-rank (id, blob) rows; vectors are stored pre-normalized."""
    q = np.asarray(query_vec, dtype=np.float32)
    scored = []
    for pid, blob in rows:
        v = unpack(blob)
        if v.shape != q.shape:
            continue  # stale model space — never mix, just skip
        scored.append((pid, float(np.dot(q, v))))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:top]
