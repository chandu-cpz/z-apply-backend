from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from z_apply_core.integrations import CoreEvent, CoreRunView

from z_apply_backend.persistence.models import RunEventRow, RunRow


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
        "browser_tab_state": view.browser_tab_state.value,
        "latest_run_sequence": view.latest_event_sequence,
        "started_at": view.started_at,
        "finished_at": view.finished_at,
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


async def reconcile_interrupted_runs(session: AsyncSession) -> None:
    await session.execute(
        update(RunRow)
        .where(
            RunRow.status.in_(("queued", "starting", "running", "waiting_human", "human_control"))
        )
        .values(
            status="terminal",
            phase="terminal",
            outcome="failed",
            summary="Backend restarted while this run was active; execution was not resumed.",
            finished_at=datetime.now(UTC),
        )
    )
