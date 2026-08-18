from __future__ import annotations

from fastapi import APIRouter
from z_apply_core.agents.model_provider import get_provider_catalog

from z_apply_backend.schemas import ProviderCatalogItem

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.get("", response_model=list[ProviderCatalogItem])
async def list_providers_catalog() -> list[ProviderCatalogItem]:
    """List available LLM providers, their default models, suggested models, and configuration status."""
    return [ProviderCatalogItem(**item) for item in get_provider_catalog()]
