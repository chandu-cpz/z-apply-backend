from __future__ import annotations

from fastapi import HTTPException
from z_apply_core.integrations import (
    BrowserControlConflict,
    BrowserUnavailable,
    CoreShuttingDown,
    HumanRequestAlreadyResolved,
    HumanRequestTypeMismatch,
    InvalidRunTransition,
    RunNotFound,
    SubmissionApprovalViolation,
)


def integration_error(exc: Exception) -> HTTPException:
    """Map the public Core exception contract to stable transport error codes."""

    if isinstance(exc, RunNotFound):
        return HTTPException(404, detail={"code": "run_not_found"})
    if isinstance(exc, BrowserUnavailable):
        return HTTPException(409, detail={"code": "browser_unavailable"})
    if isinstance(exc, BrowserControlConflict):
        return HTTPException(409, detail={"code": "browser_control_conflict"})
    if isinstance(exc, InvalidRunTransition):
        return HTTPException(409, detail={"code": "invalid_run_transition"})
    if isinstance(exc, HumanRequestAlreadyResolved):
        return HTTPException(409, detail={"code": "human_request_already_resolved"})
    if isinstance(exc, HumanRequestTypeMismatch):
        return HTTPException(409, detail={"code": "human_request_type_mismatch"})
    if isinstance(exc, SubmissionApprovalViolation):
        return HTTPException(409, detail={"code": "submission_approval_violation"})
    if isinstance(exc, CoreShuttingDown):
        return HTTPException(503, detail={"code": "core_shutting_down"})
    return HTTPException(500, detail={"code": "integration_failure"})
