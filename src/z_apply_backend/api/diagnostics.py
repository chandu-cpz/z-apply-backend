from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from z_apply_core import __version__
from z_apply_core.integrations import ZApplyCore

from z_apply_backend.config import Settings
from z_apply_backend.dependencies import core

router = APIRouter(prefix="/api/v1", tags=["diagnostics"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    return {
        "ok": True,
        "database": "connected",
        "version": __version__,
        "service": "z-apply-backend",
    }


@router.get("/diagnostics")
async def diagnostics(app_core: ZApplyCore = Depends(core)) -> dict[str, object]:
    settings = Settings()
    return {
        "version": __version__,
        "max_active_runs": settings.max_active_runs,
        "active_runs": len(app_core.active_run_ids()),
        "live_view": (await app_core.live_view()).available,
        "database": "connected",
    }


@router.get("/profile")
async def profile() -> dict[str, str]:
    return {
        "summary": "Candidate profile is managed by Z-Apply Core and is read-only in this cockpit."
    }


@router.get("/documents")
async def documents() -> list[dict[str, str]]:
    return []


@router.get("/settings")
async def settings() -> dict[str, object]:
    configured = Settings()
    return {
        "max_active_runs": configured.max_active_runs,
        "telegram_enabled": False,
        "gmail_enabled": False,
        "simplify_enabled": True,
    }
