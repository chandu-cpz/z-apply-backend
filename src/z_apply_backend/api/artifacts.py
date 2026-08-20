from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from z_apply_backend.api.errors import raise_run_not_found
from z_apply_backend.config import Settings
from z_apply_backend.persistence.database import session_scope
from z_apply_backend.persistence.models import ArtifactRow
from z_apply_backend.persistence.repositories import get_artifact, get_run, list_artifacts
from z_apply_backend.schemas import serialize_artifact_row

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


@router.get("/runs/{run_id}/artifacts")
async def artifacts(request: Request, run_id: UUID) -> list[dict[str, object]]:
    async with session_scope(request.app.state.sessions) as session:
        run = await get_run(session, run_id)
        rows = await list_artifacts(session, run_id) if run is not None else []
    if run is None:
        raise_run_not_found()
    return [_artifact_dict(item) for item in rows]


@router.get("/artifacts/{artifact_id}")
async def artifact(request: Request, artifact_id: UUID) -> FileResponse:
    async with session_scope(request.app.state.sessions) as session:
        item = await get_artifact(session, artifact_id)
    if item is None:
        raise HTTPException(404, detail={"code": "artifact_not_found"})
    root = Settings().artifact_root.resolve()
    path = (root / item.relative_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, detail={"code": "artifact_not_found"})
    return FileResponse(path, media_type=item.mime_type, filename=item.filename)


def _artifact_dict(item: ArtifactRow) -> dict[str, object]:
    return serialize_artifact_row(item)
