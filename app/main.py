"""FastAPI app entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .errors import register_error_handlers
from .routers import chat, courses, questions, resources, schedule, topics

init_db()

app = FastAPI()

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
