"""FastAPI app entrypoint — factory only, no import-time side effects.

Importing this module must never touch the database; all startup work
(init_db: backup, create, migrate, seed) runs inside create_app().
Serve with uvicorn's factory flag:
    uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .database import init_db
from .errors import register_error_handlers
from .routers import chat, courses, questions, resources, schedule, topics


class SPAStaticFiles(StaticFiles):
    """Serve a built Vite app, falling back to its client-side router."""

    async def get_response(self, path: str, scope):  # type: ignore[no-untyped-def]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)  # pipeline logs (extract/embed/images)
    init_db()
    resources.resume_pending_extractions()

    app = FastAPI()

    register_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        # Firefox extension pages run on per-install moz-extension:// origins —
        # match them by regex so the sidebar agent can call the API directly.
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|moz-extension://.+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(courses.router)
    app.include_router(topics.router)
    app.include_router(resources.router)
    app.include_router(questions.router)
    app.include_router(schedule.router)
    app.include_router(chat.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # `run.sh` builds the frontend and serves this directory from the same
    # local origin as the API. Keeping the mount optional preserves backend
    # development and test startup before `frontend/dist` exists.
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app
