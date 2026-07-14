from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from z_apply_core.integrations import (
    BrowserControlConflict,
    BrowserUnavailable,
    InvalidRunTransition,
    ZApplyCore,
)

from z_apply_backend.dependencies import core
from z_apply_backend.schemas import BrowserControlBody

router = APIRouter(prefix="/api/v1/browser", tags=["browser"])


@router.get("/live-view")
async def live_view(app_core: ZApplyCore = Depends(core)) -> dict[str, object]:
    view = await app_core.live_view()
    return {
        "available": view.available,
        "vnc_host": view.vnc_host,
        "vnc_port": view.vnc_port,
        "control_mode": view.control_mode,
        "focused_run_id": view.focused_run_id,
    }


@router.post("/take-control")
async def take_control(
    body: BrowserControlBody, app_core: ZApplyCore = Depends(core)
) -> dict[str, object]:
    try:
        view = await app_core.take_browser_control(str(body.run_id))
    except Exception as exc:
        raise _browser_error(exc) from None
    return {"run_id": view.run_id, "control_mode": view.control_mode}


@router.post("/return-control")
async def return_control(
    body: BrowserControlBody, app_core: ZApplyCore = Depends(core)
) -> dict[str, object]:
    try:
        view = await app_core.return_browser_control(str(body.run_id))
    except Exception as exc:
        raise _browser_error(exc) from None
    return {"run_id": view.run_id, "control_mode": view.control_mode}


@router.post("/close-workspace")
async def close_workspace(
    force: bool = False, app_core: ZApplyCore = Depends(core)
) -> dict[str, bool]:
    try:
        await app_core.shutdown_browser_workspace(force=force)
    except InvalidRunTransition:
        raise HTTPException(409, detail={"code": "invalid_run_transition"}) from None
    return {"closed": True}


def _browser_error(exc: Exception) -> HTTPException:
    if isinstance(exc, BrowserUnavailable):
        return HTTPException(409, detail={"code": "browser_unavailable"})
    if isinstance(exc, BrowserControlConflict):
        return HTTPException(409, detail={"code": "browser_control_conflict"})
    return HTTPException(404, detail={"code": "run_not_found"})
