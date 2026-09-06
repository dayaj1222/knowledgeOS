"""Database engine and session."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, User

DB_PATH = "knowledge_base.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    # Busy timeout: concurrent writers (chat turns vs background extraction)
    # wait for the lock instead of failing immediately with "database is
    # locked". 30s covers a slow extraction commit; chat turns are short.
    connect_args={"check_same_thread": False, "timeout": 30.0},
)


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _migrate()
    _seed_default_user()


def _migrate() -> None:
    """Lightweight additive migrations for columns added after first deploy.

    create_all() never alters existing tables, so each new nullable column
    gets an explicit ALTER TABLE here. Idempotent — checks pragma first.
    """
    from sqlalchemy import inspect, text as _text

    wanted: dict[str, list[str]] = {
        "preferences": ["ALTER TABLE preferences ADD COLUMN tutor_instructions TEXT"],
    }
    with engine.begin() as conn:
        for table, stmts in wanted.items():
            cols = {c["name"] for c in inspect(conn).get_columns(table)}
            for stmt in stmts:
                col = stmt.split("ADD COLUMN", 1)[1].strip().split()[0]
                if col not in cols:
                    conn.execute(_text(stmt))


def _seed_default_user() -> None:
    """Ensure the hardcoded user (id=1) exists — the app and frontend key on it.

    Idempotent: only inserts if missing, so a fresh or rebuilt DB always has
    the user the frontend calls, and we never 404 on the user-existence guard.
    """
    with SessionLocal() as db:
        if not db.get(User, 1):
            db.add(User(
                id=1,
                name="Student",
                email="student@localhost",
                timezone="Asia/Kolkata",
                course_name="",
                semester=1,
            ))
            db.commit()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
