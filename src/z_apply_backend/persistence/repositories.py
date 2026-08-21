from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from z_apply_core.integrations import CoreArtifact, CoreEvent, CoreHumanRequest, CoreRunView

from z_apply_backend.persistence.models import (
    ArtifactRow,
    HumanRequestRow,
    ModelCallRow,
    RunEventRow,
    RunRow,
)


def new_input_tokens(input_tokens: int, cache_read_tokens: int) -> int:
    """Non-recounted input tokens — single definition for Python and SQL.

    Provider-reported ``input_tokens`` re-sends the whole conversation on
    resumption; ``cache_read_tokens`` is the prefix-cache hit.  The SQL
    totals use ``GREATEST(input - cache, 0)`` which is semantically
    identical — see ``model_call_totals`` below.  Keep them in sync.
    """
    return max(input_tokens - cache_read_tokens, 0)


def _run_values(view: CoreRunView) -> dict[str, object]:
    return {
        "job_url": view.job_url,
        "task": view.task or "",
        "company": view.company,
        "role": view.role,
        "status": view.status.value,
        "phase": view.phase.value,
        "outcome": view.outcome.value if view.outcome else None,
        "summary": view.summary,
        "current_agent": view.current_agent,
        "current_model": view.current_model,
        "current_provider": view.current_provider,
        "browser_tab_state": view.browser_tab_state.value,
        "control_mode": view.control_mode.value,
        "pending_human_request_id": view.pending_human_request_id,
        "latest_run_sequence": view.latest_event_sequence,
        "started_at": view.started_at,
        "finished_at": view.finished_at,
        "current_reasoning": view.current_reasoning,
        "current_reasoning_effort": view.current_reasoning_effort,
    }


async def insert_run(session: AsyncSession, view: CoreRunView) -> None:
    session.add(
        RunRow(
            id=UUID(view.run_id),
            created_at=view.created_at,
            updated_at=view.created_at,
            **_run_values(view),
        )
    )


async def persist_event(session: AsyncSession, event: CoreEvent, view: CoreRunView) -> RunEventRow:
    row = RunEventRow(
        run_id=UUID(event.run_id),
        run_sequence=event.sequence,
        occurred_at=event.occurred_at,
        type=event.type,
        source=dict(event.source),
        level=event.level,
        payload=dict(event.payload),
    )
    session.add(row)
    await session.flush()
    await session.execute(
        update(RunRow).where(RunRow.id == UUID(event.run_id)).values(**_run_values(view))
    )
    return row


async def list_runs(
    session: AsyncSession,
    *,
    limit: int,
    cursor: datetime | None,
    status: str | None,
    outcome: str | None,
) -> list[RunRow]:
    statement: Select[tuple[RunRow]] = (
        select(RunRow).order_by(RunRow.created_at.desc()).limit(limit)
    )
    if cursor is not None:
        statement = statement.where(RunRow.created_at < cursor)
    if status:
        statement = statement.where(RunRow.status == status)
    if outcome:
        statement = statement.where(RunRow.outcome == outcome)
    return list((await session.scalars(statement)).all())


async def get_run(session: AsyncSession, run_id: UUID) -> RunRow | None:
    return await session.get(RunRow, run_id)


async def list_events(
    session: AsyncSession,
    *,
    after: int = 0,
    run_id: UUID | None = None,
    limit: int = 500,
    newest_first: bool = False,
) -> list[RunEventRow]:
    statement = select(RunEventRow)
    if after:
        statement = statement.where(RunEventRow.id > after)
    if run_id:
        statement = statement.where(RunEventRow.run_id == run_id)
    ordering = RunEventRow.id.desc() if newest_first else RunEventRow.id
    rows = list((await session.scalars(statement.order_by(ordering).limit(limit))).all())
    return list(reversed(rows)) if newest_first else rows


async def interrupt_active_runs(session: AsyncSession) -> list[RunEventRow]:
    """Truthfully terminate runs whose live Core process disappeared.

    Restarting a job application is unsafe: the previous process may have
    completed an irreversible browser action immediately before it died.
    """

    active_statuses = ("queued", "starting", "running", "waiting_human", "human_control")
    rows = list(
        (
            await session.scalars(
                select(RunRow).where(RunRow.status.in_(active_statuses)).with_for_update()
            )
        ).all()
    )
    occurred_at = datetime.now(UTC)
    events: list[RunEventRow] = []
    for row in rows:
        sequence = await _next_run_sequence(session, row.id, row.latest_run_sequence)
        event = RunEventRow(
            run_id=row.id,
            run_sequence=sequence,
            occurred_at=occurred_at,
            type="run.interrupted",
            source={"component": "backend", "reason": "process_restart"},
            level="warning",
            payload={
                "outcome": "interrupted",
                "summary": "Backend restarted while this application was active; it was not retried.",
            },
        )
        session.add(event)
        events.append(event)
        row.status = "terminal"
        row.phase = "terminal"
        row.outcome = "interrupted"
        row.summary = "Backend restarted while this application was active; it was not retried."
        # The process death took every browser with it; leaving "open" here
        # makes clients auto-focus a tab that no longer exists (404 on focus).
        row.browser_tab_state = "closed"
        row.latest_run_sequence = sequence
        row.finished_at = occurred_at
    await session.flush()
    return events


async def mark_run_start_failed(session: AsyncSession, run_id: UUID, error_code: str) -> None:
    row = await session.get(RunRow, run_id, with_for_update=True)
    if row is None:
        return
    occurred_at = datetime.now(UTC)
    sequence = await _next_run_sequence(session, run_id, row.latest_run_sequence)
    session.add(
        RunEventRow(
            run_id=run_id,
            run_sequence=sequence,
            occurred_at=occurred_at,
            type="run.start_failed",
            source={"component": "backend"},
            level="error",
            payload={"error_code": error_code},
        )
    )
    row.status = "terminal"
    row.phase = "terminal"
    row.outcome = "failed"
    row.summary = "Core rejected or failed to start this run."
    row.latest_run_sequence = sequence
    row.finished_at = occurred_at


async def _next_run_sequence(session: AsyncSession, run_id: UUID, cached: int) -> int:
    """Allocate after durable event truth; run metadata is only a read cache."""
    durable = await session.scalar(
        select(func.max(RunEventRow.run_sequence)).where(RunEventRow.run_id == run_id)
    )
    return max(cached, durable or 0) + 1


async def upsert_human_request(session: AsyncSession, request: CoreHumanRequest) -> None:
    values = {
        "id": UUID(request.request_id),
        "run_id": UUID(request.run_id),
        "kind": request.kind,
        "question": request.question,
        "context": request.context,
        "options": list(request.options),
        "risk": request.risk,
        "allow_free_text": request.allow_free_text,
        "image_artifact_id": (
            UUID(request.image_artifact_id) if request.image_artifact_id is not None else None
        ),
        "status": request.status,
        "answer": request.answer,
        "approved": request.approved,
        "responder": request.responder,
        "created_at": request.created_at,
        "resolved_at": request.resolved_at,
    }
    statement = pg_insert(HumanRequestRow).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[HumanRequestRow.id],
            set_={key: value for key, value in values.items() if key not in {"id", "run_id"}},
        )
    )


async def list_human_requests(session: AsyncSession, run_id: UUID) -> list[HumanRequestRow]:
    statement = (
        select(HumanRequestRow)
        .where(HumanRequestRow.run_id == run_id)
        .order_by(HumanRequestRow.created_at)
    )
    return list((await session.scalars(statement)).all())


async def upsert_artifact(session: AsyncSession, artifact: CoreArtifact) -> None:
    values = {
        "id": UUID(artifact.artifact_id),
        "run_id": UUID(artifact.run_id),
        "kind": artifact.kind,
        "filename": artifact.filename,
        "relative_path": artifact.relative_path,
        "mime_type": artifact.mime_type,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        "created_at": artifact.created_at,
    }
    statement = pg_insert(ArtifactRow).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[ArtifactRow.id],
            set_={key: value for key, value in values.items() if key not in {"id", "run_id"}},
        )
    )


async def list_artifacts(session: AsyncSession, run_id: UUID) -> list[ArtifactRow]:
    statement = (
        select(ArtifactRow).where(ArtifactRow.run_id == run_id).order_by(ArtifactRow.created_at)
    )
    return list((await session.scalars(statement)).all())


async def get_artifact(session: AsyncSession, artifact_id: UUID) -> ArtifactRow | None:
    return await session.get(ArtifactRow, artifact_id)


def _model_call_values(event: CoreEvent) -> dict[str, object]:
    """Map a durable ``model.call.metrics`` event to a ledger row.

    The event payload carries the resolved cost (gateway-reported or rate-card
    estimate) from the core's call ledger, so the DB row is auditable without
    re-deriving provider rates.
    """
    payload = event.payload
    return {
        "run_id": UUID(event.run_id),
        "sequence": event.sequence,
        "agent": str(payload.get("role") or ""),
        "model": str(payload.get("model_id") or ""),
        "provider": str(payload.get("provider") or ""),
        "input_tokens": int(payload.get("input_tokens") or 0),
        "output_tokens": int(payload.get("output_tokens") or 0),
        "cache_read_tokens": int(payload.get("cache_read_tokens") or 0),
        "ttft_ms": payload.get("ttft_ms"),
        "duration_ms": payload.get("duration_ms"),
        "tok_per_second": payload.get("tok_per_second"),
        "cost_usd": payload.get("cost_usd"),
        "occurred_at": event.occurred_at,
    }


async def insert_model_call(session: AsyncSession, event: CoreEvent) -> None:
    """Persist one successful call as a ledger row (per-call events are unique)."""
    session.add(ModelCallRow(**_model_call_values(event)))


async def list_model_calls(session: AsyncSession, run_id: UUID) -> list[ModelCallRow]:
    statement = (
        select(ModelCallRow)
        .where(ModelCallRow.run_id == run_id)
        .order_by(ModelCallRow.sequence, ModelCallRow.id)
    )
    return list((await session.scalars(statement)).all())


async def model_call_totals(session: AsyncSession, run_id: UUID) -> dict[str, float | int]:
    """SQL-derived ledger totals; never drift from the row source of truth.

    ``input_tokens`` is the gross provider-reported prompt total, which for a
    resuming agent thread re-sends the whole conversation on every call.
    ``new_input_tokens`` (input minus cache reads) is the non-recounted figure
    and the one callers should headline.  The per-row SQL uses
    ``GREATEST(input - cache, 0)`` — identical to ``new_input_tokens()``
    above.
    """
    row = (
        await session.execute(
            select(
                func.count(ModelCallRow.id),
                func.coalesce(func.sum(ModelCallRow.input_tokens), 0),
                func.coalesce(func.sum(ModelCallRow.output_tokens), 0),
                func.coalesce(func.sum(ModelCallRow.cache_read_tokens), 0),
                func.coalesce(
                    func.sum(
                        func.greatest(
                            ModelCallRow.input_tokens - ModelCallRow.cache_read_tokens, 0
                        )
                    ),
                    0,
                ),
                func.coalesce(func.sum(ModelCallRow.cost_usd), 0.0),
            ).where(ModelCallRow.run_id == run_id)
        )
    ).one()
    calls, input_tokens, output_tokens, cache_read_tokens, new_input_tokens, cost_usd = row
    return {
        "calls": int(calls or 0),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "cache_read_tokens": int(cache_read_tokens or 0),
        "new_input_tokens": int(new_input_tokens or 0),
        "cost_usd": round(float(cost_usd or 0.0), 6),
    }
