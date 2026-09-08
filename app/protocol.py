"""Standard response envelope + helpers.

Every API response is wrapped so clients have one shape to parse and a place
for request metadata. Async operations use 202 + a pollable status endpoint
rather than blocking the HTTP request.

Envelope:
    success:  {"data": <payload>, "meta": {"request_id": ...}, "error": null}
    failure:  {"data": null, "meta": {"request_id": ...},
               "error": {"type": <str>, "detail": <str>}}
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.responses import JSONResponse


def ok(data: Any = None) -> dict:
    return {"data": data, "meta": {"request_id": uuid.uuid4().hex}, "error": None}


def fail(error_type: str, detail: str, *, status_code: int = 500) -> JSONResponse:
    """Failure envelope with a REAL HTTP status (not 200).

    Previously this returned a (dict, int) tuple, which FastAPI serializes
    as a JSON array with status 200 — the frontend then treated the error
    as data and never toasted. Every fail() call site is fixed by this.
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "data": None,
            "meta": {"request_id": uuid.uuid4().hex},
            "error": {"type": error_type, "detail": detail},
        },
    )


# Terminal states for an async resource operation. The client polls until it
# sees one of these, then stops.
TERMINAL_STATUSES = {"done", "failed", "partial"}
