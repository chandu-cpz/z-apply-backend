"""Add provider and reasoning columns to runs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0008"
down_revision: str | None = "20260819_0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("current_provider", sa.String(length=80), nullable=True))
    op.add_column("runs", sa.Column("current_reasoning", sa.String(length=16), nullable=False, server_default="auto"))
    op.add_column("runs", sa.Column("current_reasoning_effort", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "current_reasoning_effort")
    op.drop_column("runs", "current_reasoning")
    op.drop_column("runs", "current_provider")
