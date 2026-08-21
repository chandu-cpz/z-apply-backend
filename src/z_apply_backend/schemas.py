from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from z_apply_core.integrations import CoreRunView

from z_apply_backend.persistence.models import ArtifactRow, HumanRequestRow, RunEventRow


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
    reasoning: Literal["auto", "off", "on"] = Field(pattern="^(auto|off|on)$")
    reasoning_effort: Literal["low", "medium", "high", "max"] | None = Field(
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
    control_mode: str = "agent_control"
    pending_human_request_id: str | None = None
    latest_run_sequence: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    current_reasoning: Literal["auto", "off", "on"] = "on"
    current_reasoning_effort: Literal["low", "medium", "high", "max"] | None = "high"

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
            control_mode=view.control_mode.value,
            pending_human_request_id=view.pending_human_request_id,
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


# ---- Shared wire DTOs — single source for runs/events/human/artifacts ----


class RunEventResponse(BaseModel):
    database_id: int = Field(alias="id")
    run_id: str
    sequence: int = Field(alias="run_sequence")
    occurred_at: datetime
    type: str
    source: dict[str, object]
    level: str
    payload: dict[str, object]

    @classmethod
    def from_row(cls, row: RunEventRow) -> RunEventResponse:
        return cls(
            id=row.id,
            run_id=str(row.run_id),
            run_sequence=row.run_sequence,
            occurred_at=row.occurred_at,
            type=row.type,
            source=row.source,
            level=row.level,
            payload=row.payload,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "database_id": self.database_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at.isoformat(),
            "type": self.type,
            "source": self.source,
            "level": self.level,
            "payload": self.payload,
        }


def serialize_event_row(row: RunEventRow) -> dict[str, object]:
    """Single helper used by both ``GET /runs/{id}/events`` and SSE ``/events/stream``."""
    return RunEventResponse.from_row(row).to_wire()


class HumanRequestResponse(BaseModel):
    request_id: str
    run_id: str
    kind: str
    question: str
    context: str
    options: list[str]
    risk: str
    allow_free_text: bool
    image_artifact_id: str | None
    status: str
    answer: str | None
    approved: bool | None
    responder: str | None
    created_at: datetime
    resolved_at: datetime | None

    @classmethod
    def from_row(cls, row: HumanRequestRow) -> HumanRequestResponse:
        return cls(
            request_id=str(row.id),
            run_id=str(row.run_id),
            kind=row.kind,
            question=row.question,
            context=row.context,
            options=row.options,
            risk=row.risk,
            allow_free_text=row.allow_free_text,
            image_artifact_id=str(row.image_artifact_id) if row.image_artifact_id else None,
            status=row.status,
            answer=row.answer,
            approved=row.approved,
            responder=row.responder,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "question": self.question,
            "context": self.context,
            "options": self.options,
            "risk": self.risk,
            "allow_free_text": self.allow_free_text,
            "image_artifact_id": self.image_artifact_id,
            "status": self.status,
            "answer": self.answer,
            "approved": self.approved,
            "responder": self.responder,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


def serialize_human_row(row: HumanRequestRow) -> dict[str, object]:
    return HumanRequestResponse.from_row(row).to_wire()


class ArtifactResponse(BaseModel):
    artifact_id: str
    run_id: str
    kind: str
    filename: str
    relative_path: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: ArtifactRow) -> ArtifactResponse:
        return cls(
            artifact_id=str(row.id),
            run_id=str(row.run_id),
            kind=row.kind,
            filename=row.filename,
            relative_path=row.relative_path,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            sha256=row.sha256,
            created_at=row.created_at,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "filename": self.filename,
            "relative_path": self.relative_path,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at": self.created_at,
        }


def serialize_artifact_row(row: ArtifactRow) -> dict[str, object]:
    return ArtifactResponse.from_row(row).to_wire()
