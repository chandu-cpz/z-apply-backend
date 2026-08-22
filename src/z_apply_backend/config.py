from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    """Nearest ancestor containing both package checkouts as siblings.

    Worktrees can nest inside their own repo, so counting levels is not
    enough; the sibling-pair marker is layout-proof.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "z-apply-core" / "pyproject.toml").is_file() and (
            candidate / "z-apply-backend" / "pyproject.toml"
        ).is_file():
            return candidate
    raise RuntimeError(
        "z-apply workspace root not found above the running source tree"
    )


class Settings(BaseSettings):
    # The workspace-root .env is the single env file for every package.
    # _repo_root anchors on sibling package checkouts (layout-proof across
    # worktrees); absolute, CWD-independent.
    model_config = SettingsConfigDict(
        env_prefix="Z_APPLY_",
        env_file=_repo_root() / ".env",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://zapply:zapply@127.0.0.1:5433/zapply"
    artifact_root: Path = Path("../z-apply-core/.z-apply/runs")
    # Single concurrency knob, clamped like the core browser pool
    # (browser_workspace._configured_max_active_runs clamps 1..8); the same
    # env var sizes the scheduler, the browser pool, and the profile slots.
    max_active_runs: int = Field(default=3, ge=1, le=8)
    cors_origin: str = "*"
