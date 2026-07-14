from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from z_apply_core.integrations import InvalidRunTransition, ZApplyCore

from z_apply_backend.api.errors import integration_error
from z_apply_backend.dependencies import core
from z_apply_backend.schemas import BrowserControlBody
from z_apply_backend.services.vnc_bridge import VncBridge

router = APIRouter(prefix="/api/v1/browser", tags=["browser"])


@router.get("/live-view")
async def live_view(request: Request, app_core: ZApplyCore = Depends(core)) -> dict[str, object]:
    view = await app_core.live_view()
    websocket_url: str | None = None
    if view.available and view.vnc_host is not None and view.vnc_port is not None:
        bridge: VncBridge = request.app.state.vnc_bridge
        access = await bridge.issue_access(view.vnc_host, view.vnc_port)
        endpoint = str(request.url_for("vnc_websocket"))
        endpoint = endpoint.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        websocket_url = f"{endpoint}?token={access.token}"
    return {
        "available": view.available,
        "vnc_host": view.vnc_host,
        "vnc_port": view.vnc_port,
        "websocket_url": websocket_url,
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
        raise integration_error(exc) from None
    return {"run_id": view.run_id, "control_mode": view.control_mode}


@router.post("/return-control")
async def return_control(
    body: BrowserControlBody, app_core: ZApplyCore = Depends(core)
) -> dict[str, object]:
    try:
        view = await app_core.return_browser_control(str(body.run_id))
    except Exception as exc:
        raise integration_error(exc) from None
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


@router.websocket("/vnc", name="vnc_websocket")
async def vnc_websocket(websocket: WebSocket, token: str = Query()) -> None:
    bridge: VncBridge = websocket.app.state.vnc_bridge
    await bridge.bridge(websocket, token)
