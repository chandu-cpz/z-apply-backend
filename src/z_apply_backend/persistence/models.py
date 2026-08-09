from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_url: Mapped[str] = mapped_column(Text)
    task: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), index=True)
    phase: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str | None] = mapped_column(String(32), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    current_agent: Mapped[str | None] = mapped_column(String(255))
    current_model: Mapped[str | None] = mapped_column(String(255))
    browser_tab_state: Mapped[str] = mapped_column(String(32))
    latest_run_sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RunEventRow(Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "run_sequence", name="uq_run_events_sequence"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("runs.id"), index=True)
    run_sequence: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[dict[str, object]] = mapped_column(JSONB)
    level: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)


class HumanRequestRow(Base):
    __tablename__ = "human_requests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSONB)
    risk: Mapped[str] = mapped_column(String(32))
    allow_free_text: Mapped[bool] = mapped_column(Boolean, default=True)
    image_artifact_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("artifacts.id")
    )
    status: Mapped[str] = mapped_column(String(32))
    answer: Mapped[str | None] = mapped_column(Text)
    approved: Mapped[bool | None] = mapped_column(Boolean)
    responder: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    relative_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelCallRow(Base):
    """One successful LLM call per run: the auditable call ledger.

    Fed from durable ``model.call.metrics`` events (one per successful call,
    carrying the resolved cost — gateway-reported or rate-card estimate). Rows
    are immutable; totals are derived with SQL aggregates so the API never
    drifts from the source of truth.
    """

    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    agent: Mapped[str] = mapped_column(String(120), default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    provider: Mapped[str] = mapped_column(String(80), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ttft_ms: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    tok_per_second: Mapped[float | None] = mapped_column(Float)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
