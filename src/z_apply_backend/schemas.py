from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class StartRunBody(BaseModel):
    job_url: HttpUrl
    task: str | None = Field(default=None, max_length=10_000)


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
    browser_tab_state: str
    latest_run_sequence: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AnswerBody(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000)


class SubmissionDecisionBody(BaseModel):
    decision: str


class BrowserControlBody(BaseModel):
    run_id: UUID
