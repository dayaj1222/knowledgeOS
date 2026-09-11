"""Database engine and session.

Single-user local-first: one SQLite file, resolved ONCE at import to an
absolute path (project root, or KB_DB_PATH override) — never the process
working directory, so booting from anywhere always opens the same database.
WAL mode lets chat turns read while an extraction writes; backups run at
startup in init_db (pre-migration state, so restore always unwinds cleanly).
"""

import os
import shutil
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base, User

BACKUP_KEEP = 10


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_db_path() -> Path:
    override = os.environ.get("KB_DB_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return project_root() / "knowledge_base.db"


DB_PATH = str(resolve_db_path())
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    # Busy timeout: concurrent writers (chat turns vs background extraction)
    # wait for the lock instead of failing immediately with "database is
    # locked". 30s covers a slow extraction commit; chat turns are short.
    connect_args={"check_same_thread": False, "timeout": 30.0},
)


@event.listens_for(engine, "connect")
def _wal_mode(dbapi_conn, _connection_record) -> None:
    # Readers (chat turns, UI polls) never block behind one writer.
    dbapi_conn.execute("PRAGMA journal_mode=WAL")


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def backup_db(db_path: str = DB_PATH, keep: int = BACKUP_KEEP) -> Path | None:
    """Timestamped copy next to the live DB; prunes to `keep` newest.

    Skips silently when there is nothing to back up yet (first boot).
    Returns the backup path, or None when skipped.
    """
    src = Path(db_path)
    if not src.exists():
        return None
    dest_dir = src.parent / "storage" / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"{src.stem}-{stamp}{src.suffix}"
    shutil.copy2(src, dest)
    for old in sorted(dest_dir.glob(f"{src.stem}-*{src.suffix}"))[: -keep]:
        old.unlink(missing_ok=True)
    return dest


def init_db() -> None:
    backup_db()
    Base.metadata.create_all(engine)
    _migrate()
    _migrate_cards()
    _seed_default_user()


def _migrate_cards() -> None:
    """One-time move of legacy role='quiz'|... messages into cards rows."""
    from .agent.cards import migrate_legacy_cards

    with SessionLocal() as db:
        moved = migrate_legacy_cards(db)
        if moved:
            print(f"migrated {moved} legacy card message(s) to cards")


def _migrate() -> None:
    """Lightweight additive migrations for columns added after first deploy.

    create_all() never alters existing tables, so each new nullable column
    gets an explicit ALTER TABLE here. Idempotent — checks pragma first.
    """
    from sqlalchemy import inspect
    from sqlalchemy import text as _text

    wanted: dict[str, list[str]] = {
        "preferences": [
            "ALTER TABLE preferences ADD COLUMN tutor_instructions TEXT",
            "ALTER TABLE preferences ADD COLUMN tutor_style VARCHAR(16) DEFAULT 'balanced'",
            "ALTER TABLE preferences ADD COLUMN tutor_verbosity VARCHAR(16) DEFAULT 'balanced'",
            "ALTER TABLE preferences ADD COLUMN default_quiz_count INTEGER DEFAULT 3",
            "ALTER TABLE preferences ADD COLUMN default_difficulty VARCHAR(16) DEFAULT 'medium'",
            "ALTER TABLE preferences ADD COLUMN review_batch_size INTEGER DEFAULT 8",
        ],
        "passages": [
            "ALTER TABLE passages ADD COLUMN section_path VARCHAR(512)",
            "ALTER TABLE passages ADD COLUMN tag_confidence FLOAT",
            "ALTER TABLE passages ADD COLUMN extra_topic_ids JSON",
        ],
        "reviews": [
            "ALTER TABLE reviews ADD COLUMN last_source VARCHAR(32)",
        ],
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


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
