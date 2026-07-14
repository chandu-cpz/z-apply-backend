from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from z_apply_core.integrations import (
    HumanRequestAlreadyResolved,
    HumanRequestTypeMismatch,
    SubmissionApprovalViolation,
    ZApplyCore,
)

from z_apply_backend.dependencies import core
from z_apply_backend.schemas import AnswerBody, SubmissionDecisionBody

router = APIRouter(prefix="/api/v1/runs/{run_id}/human-requests", tags=["human"])


@router.get("")
async def human_requests(
    run_id: UUID, app_core: ZApplyCore = Depends(core)
) -> list[dict[str, object]]:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    return [asdict(request) for request in await handle.human_requests()]


@router.post("/{request_id}/answer")
async def answer(
    request_id: UUID, run_id: UUID, body: AnswerBody, app_core: ZApplyCore = Depends(core)
) -> dict[str, object]:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    try:
        result = await handle.answer_human_request(str(request_id), body.answer, responder="web")
    except Exception as exc:
        raise _resolution_error(exc) from None
    return asdict(result)


@router.post("/{request_id}/submission-decision")
async def submission_decision(
    request_id: UUID,
    run_id: UUID,
    body: SubmissionDecisionBody,
    app_core: ZApplyCore = Depends(core),
) -> dict[str, object]:
    if body.decision not in {"approve", "reject"}:
        raise HTTPException(422, detail={"code": "invalid_submission_decision"})
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    try:
        result = await handle.decide_submission(
            str(request_id), body.decision == "approve", responder="web"
        )
    except Exception as exc:
        raise _resolution_error(exc) from None
    return asdict(result)


def _resolution_error(exc: Exception) -> HTTPException:
    if isinstance(
        exc, (HumanRequestAlreadyResolved, HumanRequestTypeMismatch, SubmissionApprovalViolation)
    ):
        return HTTPException(409, detail={"code": type(exc).__name__})
    return HTTPException(404, detail={"code": "human_request_not_found"})
