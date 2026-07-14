from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="Z_APPLY_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://zapply:zapply@127.0.0.1:5433/zapply"
    artifact_root: Path = Path("../z-apply-core/.z-apply/runs")
    max_active_runs: int = 3
    cors_origin: str = "http://127.0.0.1:5173"
