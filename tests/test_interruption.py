from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from z_apply_backend.persistence.repositories import (
    interrupt_active_runs,
    mark_run_start_failed,
)


class _ScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _Session:
    def __init__(self, rows: list[object], durable_sequence: int | None = None) -> None:
        self.rows = rows
        self.durable_sequence = durable_sequence
        self.added: list[object] = []
        self.flushed = False

    async def scalars(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self.rows)

    async def scalar(self, _statement: object) -> int | None:
        return self.durable_sequence

    async def get(self, _model: object, row_id: object, **_kwargs: object) -> object | None:
        return next((row for row in self.rows if getattr(row, "id", None) == row_id), None)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True


def _run_row(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "id": uuid4(),
        "job_url": "https://jobs.example.com/1",
        "task": "apply",
        "company": "Example",
        "role": "Engineer",
        "status": "running",
        "phase": "application",
        "outcome": None,
        "summary": None,
        "current_agent": "orchestrator",
        "current_model": "test-model",
        "current_provider": "test-provider",
        "browser_tab_state": "open",
        "control_mode": "agent_control",
        "pending_human_request_id": None,
        "current_reasoning": "on",
        "current_reasoning_effort": "high",
        "latest_run_sequence": 9,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "started_at": datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        "finished_at": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


EXPECTED_VIEW_KEYS = {
    "run_id",
    "job_url",
    "task",
    "company",
    "role",
    "status",
    "phase",
    "outcome",
    "summary",
    "current_agent",
    "current_model",
    "current_provider",
    "browser_tab_state",
    "control_mode",
    "pending_human_request_id",
    "latest_event_sequence",
    "created_at",
    "started_at",
    "finished_at",
    "current_reasoning",
    "current_reasoning_effort",
}


@pytest.mark.asyncio
async def test_active_runs_are_interrupted_without_creating_replacements() -> None:
    run = _run_row(durable_sequence=None)
    session = _Session([run], durable_sequence=12)

    events = await interrupt_active_runs(session)  # type: ignore[arg-type]

    assert len(events) == 1
    assert events[0].type == "run.interrupted"
    assert events[0].run_sequence == 13
    assert events[0].payload["outcome"] == "interrupted"
    assert run.status == "terminal"
    assert run.outcome == "interrupted"
    assert run.latest_run_sequence == 13
    assert session.added == events
    assert session.flushed


@pytest.mark.asyncio
async def test_interrupted_event_payload_carries_view_snapshot() -> None:
    run = _run_row()
    session = _Session([run], durable_sequence=12)

    events = await interrupt_active_runs(session)  # type: ignore[arg-type]

    view = events[0].payload["view"]
    assert set(view) == EXPECTED_VIEW_KEYS
    # The snapshot describes post-interruption truth, not the stale row.
    assert view["run_id"] == str(run.id)
    assert view["status"] == "terminal"
    assert view["phase"] == "terminal"
    assert view["outcome"] == "interrupted"
    assert view["summary"].startswith("Backend restarted")
    assert view["browser_tab_state"] == "closed"
    assert view["latest_event_sequence"] == 13
    assert view["job_url"] == "https://jobs.example.com/1"
    assert view["company"] == "Example"
    assert view["role"] == "Engineer"
    assert view["task"] == "apply"
    assert view["current_agent"] == "orchestrator"
    assert view["current_model"] == "test-model"
    assert view["current_provider"] == "test-provider"
    assert view["control_mode"] == "agent_control"
    assert view["pending_human_request_id"] is None
    assert view["started_at"] == "2026-01-01T00:00:01+00:00"
    assert view["finished_at"] is not None
    assert json.dumps(view)  # payload lands in a JSONB column: must be JSON-safe


@pytest.mark.asyncio
async def test_interrupted_view_handles_absent_row_fields() -> None:
    run = _run_row(
        company=None,
        role=None,
        current_agent=None,
        current_model=None,
        current_provider=None,
        pending_human_request_id=None,
        started_at=None,
        finished_at=None,
    )
    session = _Session([run], durable_sequence=4)

    events = await interrupt_active_runs(session)  # type: ignore[arg-type]

    view = events[0].payload["view"]
    for key in ("company", "role", "current_agent", "current_model", "current_provider"):
        assert view[key] is None
    assert view["started_at"] is None
    assert json.dumps(view)


@pytest.mark.asyncio
async def test_start_failed_event_payload_carries_view_snapshot() -> None:
    run = _run_row(status="starting", phase="setup")
    run_id = run.id
    session = _Session([run])

    failed = await mark_run_start_failed(session, run_id, "RuntimeError")  # type: ignore[arg-type]

    assert failed is not None
    assert failed.type == "run.start_failed"
    assert failed.run_sequence == 10
    assert failed.payload["error_code"] == "RuntimeError"
    view = failed.payload["view"]
    assert set(view) == EXPECTED_VIEW_KEYS
    assert view["run_id"] == str(run_id)
    assert view["status"] == "terminal"
    assert view["outcome"] == "failed"
    assert view["latest_event_sequence"] == 10
    assert run.status == "terminal"
    assert run.latest_run_sequence == 10
    assert session.added == [failed]
    assert json.dumps(view)


@pytest.mark.asyncio
async def test_start_failed_for_unknown_run_is_a_no_op() -> None:
    session = _Session([])

    failed = await mark_run_start_failed(session, uuid4(), "RuntimeError")  # type: ignore[arg-type]

    assert failed is None
    assert session.added == []
