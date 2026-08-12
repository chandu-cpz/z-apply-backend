"""Prompt variant identity on runs (prompt_variant + prompt_sha)."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0006"
down_revision: str | None = "20260809_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("prompt_variant", sa.String(length=255), nullable=True))
    op.add_column("runs", sa.Column("prompt_sha", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "prompt_sha")
    op.drop_column("runs", "prompt_variant")
