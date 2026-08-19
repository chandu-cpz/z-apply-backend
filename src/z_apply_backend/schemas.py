from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from z_apply_core.integrations import CoreRunView


class StartRunBody(BaseModel):
    job_url: HttpUrl
    task: str | None = Field(default=None, max_length=10_000)
    provider: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=255)


class ProviderCatalogItem(BaseModel):
    name: str
    description: str
    default_model: str
    suggested_models: list[str]
    env_key: str
    configured: bool
    is_default: bool


class SwitchModelBody(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str | None = Field(default=None, max_length=255)


class ReasoningBody(BaseModel):
    reasoning: str = Field(pattern="^(auto|off|on)$")
    reasoning_effort: str | None = Field(
        default=None, pattern="^(low|medium|high|max)$"
    )


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    job_url: str
    task: str
    company: str | None
    role: str | None
    status: str
    phase: str
    outcome: str | None
    summary: str | None
    current_agent: str | None
    current_model: str | None
    current_provider: str | None = None
    browser_tab_state: str
    latest_run_sequence: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    current_reasoning: str = "auto"
    current_reasoning_effort: str | None = None

    @classmethod
    def from_core_view(cls, view: CoreRunView) -> RunResponse:
        return cls(
            id=view.run_id,
            job_url=view.job_url,
            task=view.task or "",
            company=view.company,
            role=view.role,
            status=view.status.value,
            phase=view.phase.value,
            outcome=view.outcome.value if view.outcome else None,
            summary=view.summary,
            current_agent=view.current_agent,
            current_model=view.current_model,
            current_provider=view.current_provider,
            browser_tab_state=view.browser_tab_state.value,
            latest_run_sequence=view.latest_event_sequence,
            created_at=view.created_at,
            started_at=view.started_at,
            finished_at=view.finished_at,
            current_reasoning=view.current_reasoning,
            current_reasoning_effort=view.current_reasoning_effort,
        )


class AnswerBody(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000)


class SubmissionDecisionBody(BaseModel):
    decision: str


class BrowserControlBody(BaseModel):
    run_id: UUID


class ContextBody(BaseModel):
    content: str = Field(min_length=1, max_length=8_000)
