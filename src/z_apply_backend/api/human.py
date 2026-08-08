from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from z_apply_core.integrations import CoreRunHandle, ZApplyCore

from z_apply_backend.api.errors import integration_error
from z_apply_backend.dependencies import core
from z_apply_backend.persistence.database import session_scope
from z_apply_backend.persistence.models import HumanRequestRow, RunRow
from z_apply_backend.persistence.repositories import list_human_requests, upsert_human_request
from z_apply_backend.schemas import AnswerBody, SubmissionDecisionBody

router = APIRouter(prefix="/api/v1/runs/{run_id}/human-requests", tags=["human"])


@router.get("")
async def human_requests(
    request: Request, run_id: UUID, app_core: ZApplyCore = Depends(core)
) -> list[dict[str, object]]:
    handle = app_core.get_run(str(run_id))
    if handle is not None:
        current = await handle.human_requests()
        if current:
            async with session_scope(request.app.state.sessions, begin=True) as session:
                for item in current:
                    await upsert_human_request(session, item)
    async with session_scope(request.app.state.sessions) as session:
        rows = await list_human_requests(session, run_id)
    if handle is None and not rows:
        async with session_scope(request.app.state.sessions) as session:
            if await session.get(RunRow, run_id) is None:
                raise HTTPException(404, detail={"code": "run_not_found"})
    return [_human_dict(row) for row in rows]


@router.post("/{request_id}/answer")
async def answer(
    request: Request,
    request_id: UUID,
    run_id: UUID,
    body: AnswerBody,
    app_core: ZApplyCore = Depends(core),
) -> dict[str, object]:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    live_request_id = await _live_request_id(handle, request_id)
    if live_request_id is None:
        raise HTTPException(404, detail={"code": "human_request_not_found"})
    try:
        result = await handle.answer_human_request(live_request_id, body.answer, responder="web")
    except Exception as exc:
        raise integration_error(exc) from None
    async with session_scope(request.app.state.sessions, begin=True) as session:
        await upsert_human_request(session, result)
    return asdict(result)


@router.post("/{request_id}/submission-decision")
async def submission_decision(
    request_id: UUID,
    run_id: UUID,
    body: SubmissionDecisionBody,
    request: Request,
    app_core: ZApplyCore = Depends(core),
) -> dict[str, object]:
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(422, detail={"code": "invalid_submission_decision"})
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    live_request_id = await _live_request_id(handle, request_id)
    if live_request_id is None:
        raise HTTPException(404, detail={"code": "human_request_not_found"})
    try:
        result = await handle.decide_submission(
            live_request_id, body.decision == "approve", responder="web"
        )
    except Exception as exc:
        raise integration_error(exc) from None
    async with session_scope(request.app.state.sessions, begin=True) as session:
        await upsert_human_request(session, result)
    return asdict(result)


async def _live_request_id(handle: CoreRunHandle, request_id: UUID) -> str | None:
    """Resolve a transport UUID to Core's opaque request ID without rewriting it."""
    for item in await handle.human_requests():
        opaque_id = str(item.request_id)
        try:
            if UUID(opaque_id) == request_id:
                return opaque_id
        except ValueError:
            continue
    return None


def _human_dict(row: HumanRequestRow) -> dict[str, object]:
    return {
        "request_id": str(row.id),
        "run_id": str(row.run_id),
        "kind": row.kind,
        "question": row.question,
        "context": row.context,
        "options": row.options,
        "risk": row.risk,
        "allow_free_text": row.allow_free_text,
        "image_artifact_id": (
            str(row.image_artifact_id) if row.image_artifact_id is not None else None
        ),
        "status": row.status,
        "answer": row.answer,
        "approved": row.approved,
        "responder": row.responder,
        "created_at": row.created_at,
        "resolved_at": row.resolved_at,
    }
