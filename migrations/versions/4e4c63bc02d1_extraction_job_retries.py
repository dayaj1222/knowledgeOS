"""add extraction job retry and cancellation state

Revision ID: 4e4c63bc02d1
Revises: 3d8b17b3bb15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4e4c63bc02d1"
down_revision: str | Sequence[str] | None = "3d8b17b3bb15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("extraction_jobs") as batch:
        batch.add_column(sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("extraction_jobs") as batch:
        batch.drop_column("cancel_requested")
        batch.drop_column("next_attempt_at")
        batch.drop_column("max_attempts")
