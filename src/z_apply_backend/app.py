from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from z_apply_core.agents.providers import get_model_gateway
from z_apply_core.integrations import CoreIntegrationConfig, ZApplyCore

from z_apply_backend.api import (
    artifacts,
    browser,
    diagnostics,
    events,
    human,
    providers,
    runs,
)
from z_apply_backend.config import Settings
from z_apply_backend.persistence.database import make_engine, make_session_factory
from z_apply_backend.persistence.repositories import interrupt_active_runs
from z_apply_backend.schemas import serialize_event_row
from z_apply_backend.services.event_hub import EventHub, StoredEvent
from z_apply_backend.services.event_store import EventStore
from z_apply_backend.services.run_supervisor import RunSupervisor
from z_apply_backend.services.vnc_bridge import VncBridge

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    engine = make_engine(settings.database_url)
    sessions = make_session_factory(engine)
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    core = ZApplyCore(CoreIntegrationConfig(max_active_runs=settings.max_active_runs))
    hub = EventHub()
    async with sessions.begin() as session:
        interrupted_events = await interrupt_active_runs(session)
    # Publish only after the transaction commits so subscribers never receive
    # a row that could still roll back. Same wire shape EventStore.accept uses.
    for row in interrupted_events:
        await hub.publish(StoredEvent(row.id, row.type, serialize_event_row(row)))
    try:
        from z_apply_core.config import load_settings

        _settings = load_settings()
        _gateway = get_model_gateway(provider_name=_settings.model_provider)
        logger.info("LLM config: provider=%s model=%s", _settings.model_provider, _gateway.model_id)
    except Exception:  # noqa: BLE001 - diagnostics must never block startup
        logger.warning("LLM config: unable to resolve provider/model at startup")
    event_store = EventStore(sessions, core, hub)
    core.add_event_sink(event_store)
    await core.start()
    app.state.engine = engine
    app.state.sessions = sessions
    app.state.core = core
    app.state.event_hub = hub
    app.state.vnc_bridge = VncBridge()
    supervisor = RunSupervisor(core, sessions, hub)
    app.state.supervisor = supervisor
    try:
        yield
    finally:
        # Bound every teardown step: a stuck page or browser connection must
        # never hang uvicorn's graceful shutdown forever (the reloader then
        # cannot restart and the port stays wedged). Each step gets a hard
        # budget, and if the core cannot close the supervised browser in time,
        # the playwright/camoufox driver processes are force-killed so the
        # server process can exit and the next one can bind.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(app.state.supervisor.close(), timeout=10)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(app.state.vnc_bridge.close(), timeout=10)
        try:
            await asyncio.wait_for(core.close(), timeout=25)
        except TimeoutError:
            logger.warning("core.close() exceeded 25s; force-killing browser driver")
            await asyncio.shield(_force_kill_browser_driver())
        # Bound the pool teardown: a connection stranded by a cancelled
        # transaction must never hang uvicorn shutdown indefinitely.
        try:
            await asyncio.wait_for(engine.dispose(), timeout=10)
        except TimeoutError:
            logger.warning("engine.dispose() exceeded 10s; connections force-closed")
            await asyncio.shield(engine.dispose())


async def _force_kill_browser_driver() -> None:
    """SIGKILL the supervised browser's driver processes (last-resort teardown).

    Scans /proc for the playwright node driver and the camoufox browser started
    for this backend and kills them so the uvicorn worker can exit. Only runs
    when graceful shutdown already failed.
    """
    markers = ("playwright/driver/package/cli.js run-driver", "camoufox-bin")
    killed: list[str] = []
    try:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                cmdline = Path(entry.path, "cmdline").read_bytes().replace(b"\0", b" ").decode(
                    errors="replace"
                )
            except OSError:
                continue
            if any(marker in cmdline for marker in markers):
                try:
                    os.kill(int(entry.name), 9)
                    killed.append(f"{entry.name}:{cmdline[:60]}")
                except ProcessLookupError:
                    continue
    except OSError:
        pass
    if killed:
        logger.warning("force-killed lingering browser processes: %s", killed)


def create_app() -> FastAPI:
    app = FastAPI(title="Z-Apply Cockpit API", version="0.1.0", lifespan=lifespan)
    settings = Settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(runs.router)
    app.include_router(providers.router)
    app.include_router(events.router)
    app.include_router(human.router)
    app.include_router(browser.router)
    app.include_router(artifacts.router)
    app.include_router(diagnostics.router)
    return app
