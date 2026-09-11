"""FastAPI app entrypoint — factory only, no import-time side effects.

Importing this module must never touch the database; all startup work
(init_db: backup, create, migrate, seed) runs inside create_app().
Serve with uvicorn's factory flag:
    uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .errors import register_error_handlers
from .routers import chat, courses, questions, resources, schedule, topics


def create_app() -> FastAPI:
    init_db()

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

    return app
