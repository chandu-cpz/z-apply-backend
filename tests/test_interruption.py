from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from z_apply_backend.persistence.repositories import interrupt_active_runs


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

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_active_runs_are_interrupted_without_creating_replacements() -> None:
    run = SimpleNamespace(
        id=uuid4(),
        latest_run_sequence=9,
        status="running",
        phase="application",
        outcome=None,
        summary=None,
        finished_at=None,
    )
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
