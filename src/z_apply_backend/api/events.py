from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from z_apply_backend.persistence.repositories import list_events
from z_apply_backend.services.event_hub import EventHub

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/stream")
async def stream_events(request: Request, after: int | None = None) -> StreamingResponse:
    last_event_id = request.headers.get("last-event-id")
    cursor = after if after is not None else int(last_event_id or 0)
    hub: EventHub = request.app.state.event_hub

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        async with request.app.state.sessions() as session:
            replay = await list_events(session, after=cursor)
        for row in replay:
            cursor = row.id
            data = {
                "database_id": row.id,
                "run_id": str(row.run_id),
                "sequence": row.run_sequence,
                "occurred_at": row.occurred_at.isoformat(),
                "type": row.type,
                "source": row.source,
                "level": row.level,
                "payload": row.payload,
            }
            yield _sse(row.id, row.type, data)
        queue = await hub.register()
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    return
                if event.id > cursor:
                    cursor = event.id
                    yield _sse(event.id, event.event_type, event.data)
        finally:
            await hub.unregister(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event_id: int, event_type: str, data: Mapping[str, object]) -> str:
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"
