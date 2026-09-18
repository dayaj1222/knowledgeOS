"""SQLite connection invariants used by the application engine."""

from sqlalchemy import text

from app.database import engine


def test_sqlite_foreign_keys_are_enforced_for_every_connection():
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
