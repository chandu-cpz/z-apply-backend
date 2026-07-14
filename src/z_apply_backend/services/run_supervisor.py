from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from z_apply_core.integrations import (
    BrowserControlMode,
    BrowserTabState,
    CoreRunView,
    RunPhase,
    RunStatus,
    StartRunRequest,
    ZApplyCore,
)

from z_apply_backend.persistence.repositories import insert_run


class RunSupervisor:
    """Creates durable records before handing execution to the Core scheduler."""

    def __init__(self, core: ZApplyCore, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._core = core
        self._sessions = sessions
        self.accepting = True

    async def create(self, request: StartRunRequest) -> UUID:
        if not self.accepting:
            raise RuntimeError("run supervisor is stopping")
        run_id = str(__import__("uuid").uuid4())
        async with self._sessions.begin() as session:
            await insert_run(session, _queued_view(request, run_id))
        await self._core.start_run(request, run_id=run_id)
        return UUID(run_id)

    def get_handle(self, run_id: UUID):
        return self._core.get_run(str(run_id))

    async def close(self) -> None:
        self.accepting = False


def _queued_view(request: StartRunRequest, run_id: str) -> CoreRunView:
    from z_apply_core.integrations.models import utc_now

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
        created_at=utc_now(),
        started_at=None,
        finished_at=None,
    )
