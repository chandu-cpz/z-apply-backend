from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from z_apply_core.integrations import InvalidRunTransition, StartRunRequest, ZApplyCore

from z_apply_backend.dependencies import core, supervisor
from z_apply_backend.persistence.repositories import get_run, list_events, list_runs
from z_apply_backend.schemas import RunResponse, StartRunBody
from z_apply_backend.services.run_supervisor import RunSupervisor

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post("", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    body: StartRunBody, service: RunSupervisor = Depends(supervisor)
) -> RunResponse:
    run_id = await service.create(StartRunRequest(job_url=str(body.job_url), task=body.task))
    # The supervisor persisted the initial view, but a direct Core view is the freshest source.
    handle = service.get_handle(run_id)
    assert handle is not None
    return RunResponse.from_core_view(await handle.view())


@router.get("", response_model=list[RunResponse])
async def get_runs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: datetime | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    outcome: str | None = None,
) -> list[RunResponse]:
    async with request.app.state.sessions() as session:
        rows = await list_runs(
            session, limit=limit, cursor=cursor, status=status_filter, outcome=outcome
        )
    return [RunResponse.model_validate(row) for row in rows]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_detail(request: Request, run_id: UUID) -> RunResponse:
    async with request.app.state.sessions() as session:
        row = await get_run(session, run_id)
    if row is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    return RunResponse.model_validate(row)


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: UUID, app_core: ZApplyCore = Depends(core)) -> RunResponse:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    try:
        await handle.cancel()
    except InvalidRunTransition:
        raise HTTPException(409, detail={"code": "invalid_run_transition"}) from None
    return RunResponse.from_core_view(await handle.view())


@router.post("/{run_id}/focus", response_model=RunResponse)
async def focus_run(run_id: UUID, app_core: ZApplyCore = Depends(core)) -> RunResponse:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    try:
        return RunResponse.from_core_view(await handle.focus_browser())
    except Exception as exc:
        raise _integration_error(exc) from None


@router.delete("/{run_id}/browser", response_model=RunResponse)
async def close_browser(run_id: UUID, app_core: ZApplyCore = Depends(core)) -> RunResponse:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    try:
        return RunResponse.from_core_view(await handle.close_browser())
    except Exception as exc:
        raise _integration_error(exc) from None


@router.get("/{run_id}/events")
async def run_events(
    request: Request, run_id: UUID, after: int = 0
) -> list[dict[str, object]]:
    async with request.app.state.sessions() as session:
        rows = await list_events(session, after=after, run_id=run_id)
    return [
        {
            "database_id": row.id,
            "run_id": str(row.run_id),
            "sequence": row.run_sequence,
            "occurred_at": row.occurred_at.isoformat(),
            "type": row.type,
            "source": row.source,
            "level": row.level,
            "payload": row.payload,
        }
        for row in rows
    ]


def _integration_error(exc: Exception) -> HTTPException:
    from z_apply_core.integrations import BrowserUnavailable, InvalidRunTransition

    if isinstance(exc, BrowserUnavailable):
        return HTTPException(409, detail={"code": "browser_unavailable"})
    if isinstance(exc, InvalidRunTransition):
        return HTTPException(409, detail={"code": "invalid_run_transition"})
    return HTTPException(409, detail={"code": "browser_control_conflict"})
