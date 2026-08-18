from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from z_apply_core.integrations.models import CoreEvent

from z_apply_backend.api.events import router


class FakeCore:
    def __init__(self, events: list[CoreEvent | None]) -> None:
        self._events = events

    async def subscribe_live(self, *, keepalive: float | None = None):  # type: ignore[no-untyped-def]
        for event in self._events:
            yield event


def _event(sequence: int, *, run_id: str = "run-1") -> CoreEvent:
    return CoreEvent(
        run_id=run_id,
        sequence=sequence,
        occurred_at=datetime.now(UTC),
        type="agent.message.delta",
        source={"component": "graph", "agent": "orchestrator"},
        level="info",
        payload={"kind": "text", "delta": f"t{sequence}"},
    )


def _app(core: FakeCore) -> FastAPI:
    app = FastAPI()
    app.state.core = core
    app.include_router(router)
    return app


async def _read_frames(url: str, core: FakeCore) -> list[str]:
    transport = httpx.ASGITransport(app=_app(core))
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream("GET", url) as response,
    ):
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["x-accel-buffering"] == "no"
            assert response.headers["cache-control"] == "no-cache"
            return [line async for line in response.aiter_lines()]


@pytest.mark.asyncio
async def test_live_sse_frames_events_and_keepalive_comments() -> None:
    core = FakeCore([_event(1), None, _event(2)])
    lines = await _read_frames("/api/v1/events/live", core)

    assert ": z-apply keepalive" in lines
    assert any(line == "id: 1" for line in lines)
    assert any(line == "event: agent.message.delta" for line in lines)
    data_lines = [line for line in lines if line.startswith("data: ")]
    assert len(data_lines) == 2
    payload = __import__("json").loads(data_lines[0][len("data: ") :])
    assert payload["run_id"] == "run-1"
    assert payload["sequence"] == 1
    assert payload["payload"] == {"kind": "text", "delta": "t1"}


@pytest.mark.asyncio
async def test_live_sse_run_filter_drops_other_runs() -> None:
    core = FakeCore([_event(1, run_id="run-a"), _event(2, run_id="run-b")])
    lines = await _read_frames("/api/v1/events/live?run_id=run-a", core)

    ids = [line for line in lines if line.startswith("id: ")]
    assert ids == ["id: 1"]


@pytest.mark.asyncio
async def test_live_sse_ends_when_core_stream_exhausts() -> None:
    core = FakeCore([_event(1)])
    lines = await _read_frames("/api/v1/events/live", core)

    assert any(line == "id: 1" for line in lines)
    assert not any(line.startswith("id: 2") for line in lines)
