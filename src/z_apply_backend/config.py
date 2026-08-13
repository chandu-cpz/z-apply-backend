from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="Z_APPLY_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://zapply:zapply@127.0.0.1:5433/zapply"
    artifact_root: Path = Path("../z-apply-core/.z-apply/runs")
    # Single concurrency knob, clamped like the core browser pool
    # (browser_workspace._configured_max_active_runs clamps 1..8); the same
    # env var sizes the scheduler, the browser pool, and the profile slots.
    max_active_runs: int = Field(default=3, ge=1, le=8)
    cors_origin: str = "*"
