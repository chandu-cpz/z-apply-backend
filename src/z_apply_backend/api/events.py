from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from z_apply_backend.persistence.database import session_scope
from z_apply_backend.persistence.models import RunEventRow
from z_apply_backend.persistence.repositories import list_events, max_event_id
from z_apply_backend.schemas import serialize_event_row
from z_apply_backend.services.event_hub import EventHub

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("/stream")
async def stream_events(
    request: Request, after: int | None = Query(default=None, ge=0)
) -> StreamingResponse:
    last_event_id = request.headers.get("last-event-id")
    try:
        # Last-Event-ID wins over ?after=: the browser sends the header (from
        # our ``id:`` frames) on every EventSource reconnect, so resuming from
        # the live cursor must beat the frozen cursor baked into the URL at
        # connect time. ?after= only applies to the initial subscription,
        # where no header exists yet. Preferring ?after= here caused every
        # reconnect to replay the full history from the original cursor.
        cursor = int(last_event_id) if last_event_id else (after or 0)
    except ValueError:
        raise HTTPException(422, detail={"code": "invalid_event_cursor"}) from None
    if cursor < 0:
        raise HTTPException(422, detail={"code": "invalid_event_cursor"})
    hub: EventHub = request.app.state.event_hub

    async def stream() -> AsyncIterator[str]:
        nonlocal cursor
        # Subscribe before replaying committed rows. Anything committed while
        # replay runs lands in this queue and is deduplicated by database id.
        queue = await hub.register()
        try:
            # A cursor beyond the stored history means the client's localStorage
            # survived a database reset (or a restore to an earlier snapshot):
            # every future event would sit at or below the cursor and be dropped
            # forever, with REST bootstrap masking it until the next refresh.
            # Tell the client to drop its cursor and replay from the start.
            async with session_scope(request.app.state.sessions) as session:
                stored_max = await max_event_id(session)
            if cursor > stored_max:
                cursor = 0
                yield _sse(stored_max, "cursor.reset", {"max_database_id": stored_max})
            page_size = 500
            while not await request.is_disconnected():
                async with session_scope(request.app.state.sessions) as session:
                    replay = await list_events(session, after=cursor, limit=page_size)
                for row in replay:
                    cursor = row.id
                    yield _sse(row.id, row.type, _stored_row(row))
                if len(replay) < page_size:
                    break
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


@router.get("/live")
async def stream_live_events(
    request: Request,
    run_id: str | None = Query(default=None),
) -> StreamingResponse:
    """Stream high-frequency, non-persisted events (reasoning/text/tool-call
    deltas) straight from the running core run. No DB replay: only events the
    core publishes live to its live broadcaster. On reconnect, EventSource's
    bounded broadcaster replay tail is re-delivered and the client drops
    duplicates itself (it dedupes per run by sequence), so the server must not
    cursor-skip here: sequences are per-run, and a global cursor built from one
    run's watermark silently swallowed other runs' deltas.

    Silent stretches (long tool executions) emit an SSE comment every 15s so
    proxies and load balancers with idle timeouts never kill the connection.
    """
    core = request.app.state.core

    async def stream() -> AsyncIterator[str]:
        async for event in core.subscribe_live(keepalive=15.0):
            if await request.is_disconnected():
                break
            if event is None:
                yield ": z-apply keepalive\n\n"
                continue
            if run_id is not None and event.run_id != run_id:
                continue
            yield _sse(event.sequence, event.type, event.to_dict())

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _stored_row(row: RunEventRow) -> dict[str, object]:
    return serialize_event_row(row)


def _sse(event_id: int, event_type: str, data: Mapping[str, object]) -> str:
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"
