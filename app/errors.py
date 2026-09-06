"""Global error handling: every response uses the standard envelope.

Success: {"data": <payload>, "meta": {"request_id": ...}, "error": null}
Failure: {"data": null, "meta": {"request_id": ...}, "error": {"type", "detail"}}

HTTPException raised anywhere (404s, 409s from services) is wrapped into the
same envelope, so the frontend parses exactly one shape. Never leaks
tracebacks; logs server-side.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

log = logging.getLogger("knowledge-base")


def _envelope_error(error_type: str, detail) -> dict:
    return {
        "data": None,
        "meta": {"request_id": uuid.uuid4().hex},
        "error": {"type": error_type, "detail": detail},
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # 422 with the actual field errors, not a bare 500
        return JSONResponse(
            status_code=422,
            content=_envelope_error("validation", exc.errors()),
        )

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        # service/route raises (404, 409, ...) -> same envelope as fail()
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope_error("http", exc.detail),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        # unique/FK violations are client-recoverable, not a crash
        return JSONResponse(
            status_code=409,
            content=_envelope_error(
                "conflict",
                "That operation conflicts with existing data (duplicate or missing reference).",
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db(request: Request, exc: SQLAlchemyError):
        log.exception("Database error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_envelope_error("database", "Database error."),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_envelope_error("internal", "Unexpected error."),
        )
