from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from z_apply_core.integrations import InvalidRunTransition, StartRunRequest, ZApplyCore

from z_apply_backend.api.errors import integration_error
from z_apply_backend.dependencies import core, supervisor
from z_apply_backend.persistence.database import session_scope
from z_apply_backend.persistence.models import RunEventRow, RunRow
from z_apply_backend.persistence.repositories import (
    get_run,
    list_events,
    list_model_calls,
    list_runs,
    model_call_totals,
)
from z_apply_backend.schemas import ContextBody, RunResponse, StartRunBody
from z_apply_backend.services.run_supervisor import RunSupervisor

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("/{run_id}/log", response_class=PlainTextResponse)
async def run_log(request: Request, run_id: UUID, limit: int = Query(default=500, ge=1, le=5000)) -> PlainTextResponse:
    """A human-readable, chronological plain-text log of one run.

    No SQL needed to understand what happened: each line carries the wall-clock
    time, the agent, the event kind, and a compact summary (turn text, tool
    call + outcome, human handoffs, phase changes, recoveries).
    """
    async with session_scope(request.app.state.sessions) as session:
        if await session.get(RunRow, run_id) is None:
            raise HTTPException(404, detail={"code": "run_not_found"})
        rows = await list_events(
            session,
            run_id=run_id,
            limit=limit,
        )
    return PlainTextResponse("\n".join(_render_log_line(row) for row in rows))


def _render_log_line(row: RunEventRow) -> str:
    occurred = row.occurred_at.strftime("%H:%M:%S")
    payload = row.payload or {}
    kind = row.type
    summary = _log_summary(kind, payload)
    agent = payload.get("agent") or payload.get("agent_path") or payload.get("role") or "-"
    return f"{occurred} [{kind:<28}] {str(agent)[:24]:<24} {summary}"


def _log_summary(kind: str, payload: dict[str, object]) -> str:
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return _clip(text, 140)
    if kind.startswith("tool."):
        tool = payload.get("tool_name", "")
        if kind == "tool.started":
            return f"{tool} {_clip(str(payload.get("input") or ""), 90)}"
        error = payload.get("error")
        output = payload.get("output")
        status = output.get("status") if isinstance(output, dict) else None
        if error:
            return f"{tool} -> ERROR: {_clip(str(error), 120)}"
        return f"{tool} -> {status or 'ok'}"
    if kind == "run.phase_changed":
        return f"phase -> {payload.get('phase', '')}"
    if kind == "human.requested":
        return f"HUMAN ASKED ({payload.get('kind', 'question')}): {_clip(str(payload.get('question') or payload.get('context') or ''), 120)}"
    if kind == "human.resolved":
        return f"HUMAN ANSWERED: {_clip(str(payload.get('answer') or ''), 60)}"
    if kind in ("recovery.started",):
        return f"RECOVERY: {_clip(str(payload.get('error') or ''), 120)}"
    if kind in ("authentication.evidence",):
        return f"auth {payload.get('status', '')}: {_clip(str(payload.get('summary') or ''), 120)}"
    if kind in ("run.queued", "run.started", "run.terminal", "run.phase_changed", "graph.event"):
        return _clip(str(payload.get("summary") or payload.get("outcome") or ""), 120) or kind
    if kind == "submission.approval_requested":
        return f"APPROVAL REQUESTED: {_clip(str(payload.get('context') or ''), 120)}"
    return _clip(str(payload)[:140], 140)


def _clip(value: str, limit: int) -> str:
    value = value.replace("\n", " ").strip()
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


@router.post("", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    body: StartRunBody, service: RunSupervisor = Depends(supervisor)
) -> RunResponse:
    try:
        run_id = await service.create(
            StartRunRequest(
                job_url=str(body.job_url),
                task=body.task,
                prompt_variant=body.prompt_variant,
                prompt_sha=body.prompt_sha,
            )
        )
    except Exception as exc:
        raise integration_error(exc) from None
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
    async with session_scope(request.app.state.sessions) as session:
        rows = await list_runs(
            session, limit=limit, cursor=cursor, status=status_filter, outcome=outcome
        )
    return [RunResponse.model_validate(row) for row in rows]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_detail(request: Request, run_id: UUID) -> RunResponse:
    async with session_scope(request.app.state.sessions) as session:
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
        raise integration_error(exc) from None


@router.post("/{run_id}/context")
async def send_context(
    run_id: UUID, body: ContextBody, app_core: ZApplyCore = Depends(core)
) -> dict[str, object]:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    try:
        return asdict(await handle.send_context(body.content, source="web"))
    except Exception as exc:
        raise integration_error(exc) from None


@router.delete("/{run_id}/browser", response_model=RunResponse)
async def close_browser(run_id: UUID, app_core: ZApplyCore = Depends(core)) -> RunResponse:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    try:
        return RunResponse.from_core_view(await handle.close_browser())
    except Exception as exc:
        raise integration_error(exc) from None


@router.get("/{run_id}/calls")
async def run_calls(request: Request, run_id: UUID) -> dict[str, object]:
    """Per-run LLM call ledger: one row per successful model call plus
    SQL-derived totals. Every call's tokens, cache hits, TTFT, throughput, and
    resolved cost are auditable here regardless of how the run was started
    (CLI or cockpit) — the backend path now persists the ledger the CLI used
    to keep to itself.
    """
    async with session_scope(request.app.state.sessions) as session:
        if await session.get(RunRow, run_id) is None:
            raise HTTPException(404, detail={"code": "run_not_found"})
        rows = await list_model_calls(session, run_id)
        totals = await model_call_totals(session, run_id)
    return {
        "run_id": str(run_id),
        "totals": totals,
        "calls": [
            {
                "sequence": row.sequence,
                "agent": row.agent,
                "model": row.model,
                "provider": row.provider,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "cache_read_tokens": row.cache_read_tokens,
                "ttft_ms": row.ttft_ms,
                "duration_ms": row.duration_ms,
                "tok_per_second": row.tok_per_second,
                "cost_usd": row.cost_usd,
                "occurred_at": row.occurred_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.get("/{run_id}/events")
async def run_events(
    request: Request,
    run_id: UUID,
    after: int | None = None,
    limit: int = Query(default=120, ge=1, le=500),
) -> list[dict[str, object]]:
    async with session_scope(request.app.state.sessions) as session:
        rows = await list_events(
            session,
            after=after or 0,
            run_id=run_id,
            limit=limit,
            newest_first=after is None,
        )
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
