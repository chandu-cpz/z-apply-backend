from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from z_apply_core.agents.prompts import (
    list_prompt_variants,
    prompt_sha,
    resolve_orchestrator_prompt,
)

router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])


class PromptVariantResponse(BaseModel):
    name: str
    sha: str
    is_default: bool


@router.get("", response_model=list[PromptVariantResponse])
async def list_prompts() -> list[PromptVariantResponse]:
    """List available orchestrator prompt variants for the run-creation UI."""
    default = resolve_orchestrator_prompt(None)
    return [
        PromptVariantResponse(
            name=name,
            sha=prompt_sha(name),
            is_default=(name == default),
        )
        for name in list_prompt_variants()
    ]
