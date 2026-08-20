from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from z_apply_core.integrations import CoreEvent, ZApplyCore

from z_apply_backend.persistence.database import session_scope
from z_apply_backend.persistence.repositories import (
    insert_model_call,
    persist_event,
    upsert_artifact,
    upsert_human_request,
)
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
        # View is required for every event (persist_event updates RunRow).
        view = await handle.view()
        # Conditionally fetch only the collections needed for this event type
        # to avoid O(H+A) write amplification on unrelated events.
        human_requests = None
        artifacts = None
        if event.type.startswith("human."):
            human_requests = await handle.human_requests()
        if event.type == "artifact.created":
            artifacts = await handle.artifacts()
        async with session_scope(self._sessions, begin=True) as session:
            row = await persist_event(session, event, view)
            if event.type == "model.call.metrics":
                # One ledger row per successful LLM call (auditable token/cost
                # history); totals are SQL-derived at read time.
                await insert_model_call(session, event)
            if human_requests is not None:
                for human_request in human_requests:
                    await upsert_human_request(session, human_request)
            if artifacts is not None:
                for artifact in artifacts:
                    await upsert_artifact(session, artifact)
            stored = StoredEvent(row.id, event.type, {"database_id": row.id, **event.to_dict()})
        await self._hub.publish(stored)
