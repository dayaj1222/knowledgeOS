"""Fresh databases must be created by Alembic, not SQLAlchemy create_all."""

import os
import subprocess
import sys


def test_init_db_upgrades_a_fresh_database_with_alembic(tmp_path):
    db_path = tmp_path / "fresh.db"
    script = """
from sqlalchemy import inspect, text
from app.database import engine, init_db

init_db()
tables = set(inspect(engine).get_table_names())
assert {'users', 'courses', 'alembic_version'} <= tables
with engine.connect() as conn:
    assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
"""
    env = {**os.environ, "KB_DB_PATH": str(db_path)}
    subprocess.run([sys.executable, "-c", script], check=True, env=env)
