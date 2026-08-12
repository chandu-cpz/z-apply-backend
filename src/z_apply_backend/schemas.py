from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from z_apply_core.integrations import CoreRunView


class StartRunBody(BaseModel):
    job_url: HttpUrl
    task: str | None = Field(default=None, max_length=10_000)
    prompt_variant: str | None = Field(default=None, max_length=255)
    prompt_sha: str | None = Field(default=None, max_length=64)


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    job_url: str
    task: str
    company: str | None
    role: str | None
    prompt_variant: str | None = None
    prompt_sha: str | None = None
    status: str
    phase: str
    outcome: str | None
    summary: str | None
    current_agent: str | None
    current_model: str | None
    browser_tab_state: str
    latest_run_sequence: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_core_view(cls, view: CoreRunView) -> RunResponse:
        return cls(
            id=view.run_id,
            job_url=view.job_url,
            task=view.task or "",
            company=view.company,
            role=view.role,
            prompt_variant=view.prompt_variant,
            prompt_sha=view.prompt_sha,
            status=view.status.value,
            phase=view.phase.value,
            outcome=view.outcome.value if view.outcome else None,
            summary=view.summary,
            current_agent=view.current_agent,
            current_model=view.current_model,
            browser_tab_state=view.browser_tab_state.value,
            latest_run_sequence=view.latest_event_sequence,
            created_at=view.created_at,
            started_at=view.started_at,
            finished_at=view.finished_at,
        )


class AnswerBody(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000)


class SubmissionDecisionBody(BaseModel):
    decision: str


class BrowserControlBody(BaseModel):
    run_id: UUID


class ContextBody(BaseModel):
    content: str = Field(min_length=1, max_length=8_000)
