from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from z_apply_backend.app import create_app
from z_apply_backend.schemas import ProviderCatalogItem, StartRunBody, SwitchModelBody


def test_start_run_body_accepts_provider_and_model() -> None:
    body = StartRunBody(
        job_url="https://example.com/careers/123",
        task="Custom task",
        provider="groq",
        model="llama-3.3-70b-versatile",
    )
    assert body.provider == "groq"
    assert body.model == "llama-3.3-70b-versatile"


def test_switch_model_body_validation() -> None:
    body = SwitchModelBody(provider="opengateway", model="inclusionai/ling-3.0-flash:free")
    assert body.provider == "opengateway"
    assert body.model == "inclusionai/ling-3.0-flash:free"


@pytest.mark.asyncio
async def test_providers_catalog_endpoint() -> None:
    from z_apply_backend.api.providers import list_providers_catalog

    items = await list_providers_catalog()
    assert len(items) >= 5
    names = [item.name for item in items]
    assert "opengateway" in names
    assert "groq" in names
    for item in items:
        assert isinstance(item, ProviderCatalogItem)
        assert item.default_model
        assert isinstance(item.suggested_models, list)
