from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from z_apply_core.integrations import ZApplyCore

from z_apply_backend.config import Settings
from z_apply_backend.dependencies import core

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


@router.get("/runs/{run_id}/artifacts")
async def artifacts(run_id: UUID, app_core: ZApplyCore = Depends(core)) -> list[dict[str, object]]:
    handle = app_core.get_run(str(run_id))
    if handle is None:
        raise HTTPException(404, detail={"code": "run_not_found"})
    return [asdict(item) for item in await handle.artifacts()]


@router.get("/artifacts/{artifact_id}")
async def artifact(artifact_id: UUID, app_core: ZApplyCore = Depends(core)) -> FileResponse:
    for run_id in app_core.active_run_ids():
        handle = app_core.get_run(run_id)
        if handle is None:
            continue
        for item in await handle.artifacts():
            if item.artifact_id != str(artifact_id):
                continue
            root = Settings().artifact_root.resolve()
            path = (root / item.relative_path).resolve()
            if root not in path.parents or not path.is_file():
                raise HTTPException(404, detail={"code": "artifact_not_found"})
            return FileResponse(path, media_type=item.mime_type, filename=item.filename)
    raise HTTPException(404, detail={"code": "artifact_not_found"})
