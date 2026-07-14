"""Persist whether a human request accepts free-form answers."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260714_0003"
down_revision: str | None = "20260714_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "human_requests",
        sa.Column("allow_free_text", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("human_requests", "allow_free_text")
