from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from z_apply_core.integrations import CoreEvent, ZApplyCore

from z_apply_backend.persistence.repositories import persist_event
from z_apply_backend.services.event_hub import EventHub, StoredEvent


class EventStore:
    """Durably write Core events before making them observable over SSE."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], core: ZApplyCore, hub: EventHub
    ) -> None:
        self._sessions = sessions
        self._core = core
        self._hub = hub

    async def accept(self, event: CoreEvent) -> None:
        handle = self._core.get_run(event.run_id)
        if handle is None:
            return
        view = await handle.view()
        async with self._sessions.begin() as session:
            row = await persist_event(session, event, view)
            stored = StoredEvent(row.id, event.type, {"database_id": row.id, **event.to_dict()})
        await self._hub.publish(stored)
