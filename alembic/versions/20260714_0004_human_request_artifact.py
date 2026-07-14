"""Link human requests to a browser-safe challenge artifact."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260714_0004"
down_revision: str | None = "20260714_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "human_requests",
        sa.Column("image_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_human_requests_image_artifact_id",
        "human_requests",
        "artifacts",
        ["image_artifact_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_human_requests_image_artifact_id", "human_requests", type_="foreignkey")
    op.drop_column("human_requests", "image_artifact_id")
