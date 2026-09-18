"""persist chat image attachments

Revision ID: af8c9d2e1b70
Revises: 4e4c63bc02d1
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "af8c9d2e1b70"
down_revision: str | Sequence[str] | None = "4e4c63bc02d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch:
        batch.add_column(sa.Column("images", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_column("images")
