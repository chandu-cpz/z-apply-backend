"""Drop prompt variant identity on runs (single fixed orchestrator prompt)."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260819_0007"
down_revision: str | None = "20260812_0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("runs", "prompt_sha")
    op.drop_column("runs", "prompt_variant")


def downgrade() -> None:
    op.add_column("runs", sa.Column("prompt_variant", sa.String(length=255), nullable=True))
    op.add_column("runs", sa.Column("prompt_sha", sa.String(length=64), nullable=True))