"""Add control_mode and pending_human_request_id to runs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0009"
down_revision: str | None = "20260821_0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("control_mode", sa.String(length=32), nullable=False, server_default="agent_control"))
    op.add_column("runs", sa.Column("pending_human_request_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "pending_human_request_id")
    op.drop_column("runs", "control_mode")
