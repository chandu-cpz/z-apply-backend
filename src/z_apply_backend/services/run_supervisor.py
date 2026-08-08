from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from z_apply_core.integrations import (
    BrowserControlMode,
    BrowserTabState,
    CoreRunHandle,
    CoreRunView,
    RunPhase,
    RunStatus,
    StartRunRequest,
    ZApplyCore,
)

from z_apply_backend.persistence.database import session_scope
from z_apply_backend.persistence.repositories import insert_run, mark_run_start_failed


class RunSupervisor:
    """Creates durable records before handing execution to the Core scheduler."""

    def __init__(self, core: ZApplyCore, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._core = core
        self._sessions = sessions
        self.accepting = True
        self._observers: set[asyncio.Task[None]] = set()

    async def create(self, request: StartRunRequest) -> UUID:
        if not self.accepting:
            raise RuntimeError("run supervisor is stopping")
        run_id = str(uuid4())
        async with session_scope(self._sessions, begin=True) as session:
            await insert_run(session, _queued_view(request, run_id))
        try:
            handle = await self._core.start_run(request, run_id=run_id)
        except Exception as exc:
            async with session_scope(self._sessions, begin=True) as session:
                await mark_run_start_failed(session, UUID(run_id), type(exc).__name__)
            raise
        observer = asyncio.create_task(self._observe(handle), name=f"observe-core-run-{run_id}")
        self._observers.add(observer)
        observer.add_done_callback(self._observers.discard)
        return UUID(run_id)

    def get_handle(self, run_id: UUID) -> CoreRunHandle | None:
        return self._core.get_run(str(run_id))

    async def close(self) -> None:
        self.accepting = False
        observers = tuple(self._observers)
        for observer in observers:
            observer.cancel()
        if observers:
            await asyncio.gather(*observers, return_exceptions=True)

    @staticmethod
    async def _observe(handle: CoreRunHandle) -> None:
        """Own the wait task so observer failures never become orphaned tasks."""

        try:
            await handle.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Core reports execution failure through typed terminal events. An
            # observer failure must not become an un-retrieved task exception.
            return


def _queued_view(request: StartRunRequest, run_id: str) -> CoreRunView:
    return CoreRunView(
        run_id=run_id,
        job_url=request.job_url,
        task=request.task,
        company=None,
        role=None,
        status=RunStatus.QUEUED,
        phase=RunPhase.QUEUED,
        outcome=None,
        summary=None,
        current_agent=None,
        current_model=None,
        browser_tab_state=BrowserTabState.PENDING,
        control_mode=BrowserControlMode.AGENT_CONTROL,
        pending_human_request_id=None,
        latest_event_sequence=0,
        created_at=datetime.now(UTC),
        started_at=None,
        finished_at=None,
    )
