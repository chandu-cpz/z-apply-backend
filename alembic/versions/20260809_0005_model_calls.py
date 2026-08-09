"""Per-run model call ledger (auditable token/cost rows per LLM call)."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260809_0005"
down_revision: str | None = "20260714_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("agent", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("provider", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("tok_per_second", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_calls_run_id", "model_calls", ["run_id"])
    op.create_index("ix_model_calls_occurred_at", "model_calls", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_model_calls_occurred_at", table_name="model_calls")
    op.drop_index("ix_model_calls_run_id", table_name="model_calls")
    op.drop_table("model_calls")
