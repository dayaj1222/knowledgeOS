"""give conversations permanent provider thread IDs

Revision ID: c1e5a4b7d2f9
Revises: af8c9d2e1b70
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1e5a4b7d2f9"
down_revision: str | Sequence[str] | None = "af8c9d2e1b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add nullable first. Existing conversations retain their legacy proxy
    # identity so their DeepSeek web history remains available; new rows use
    # random IDs and therefore can never collide after a local deletion.
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("provider_thread_id", sa.String(length=32), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, user_id FROM conversations")).all()
    for conversation_id, user_id in rows:
        bind.execute(
            sa.text("UPDATE conversations SET provider_thread_id = :thread_id WHERE id = :id"),
            {"id": conversation_id, "thread_id": f"u{user_id}_c{conversation_id}"},
        )

    with op.batch_alter_table("conversations") as batch:
        batch.alter_column("provider_thread_id", nullable=False)
        batch.create_unique_constraint(
            "uq_conversations_provider_thread_id", ["provider_thread_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("uq_conversations_provider_thread_id", type_="unique")
        batch.drop_column("provider_thread_id")
