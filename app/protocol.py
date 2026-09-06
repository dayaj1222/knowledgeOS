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


def ok(data: Any = None) -> dict:
    return {"data": data, "meta": {"request_id": uuid.uuid4().hex}, "error": None}


def fail(error_type: str, detail: str, *, status_code: int = 500) -> tuple[dict, int]:
    return (
        {
            "data": None,
            "meta": {"request_id": uuid.uuid4().hex},
            "error": {"type": error_type, "detail": detail},
        },
        status_code,
    )


# Terminal states for an async resource operation. The client polls until it
# sees one of these, then stops.
TERMINAL_STATUSES = {"done", "failed", "partial"}
