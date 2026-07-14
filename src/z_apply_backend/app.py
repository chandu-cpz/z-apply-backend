from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from z_apply_core.integrations import CoreIntegrationConfig, ZApplyCore

from z_apply_backend.api import artifacts, browser, diagnostics, events, human, runs
from z_apply_backend.config import Settings
from z_apply_backend.persistence.database import make_engine, make_session_factory
from z_apply_backend.persistence.repositories import reconcile_interrupted_runs
from z_apply_backend.services.event_hub import EventHub
from z_apply_backend.services.event_store import EventStore
from z_apply_backend.services.run_supervisor import RunSupervisor


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    engine = make_engine(settings.database_url)
    sessions = make_session_factory(engine)
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    async with sessions.begin() as session:
        await reconcile_interrupted_runs(session)
    core = ZApplyCore(CoreIntegrationConfig(max_active_runs=settings.max_active_runs))
    hub = EventHub()
    event_store = EventStore(sessions, core, hub)
    core.add_event_sink(event_store)
    await core.start()
    app.state.engine = engine
    app.state.sessions = sessions
    app.state.core = core
    app.state.event_hub = hub
    app.state.supervisor = RunSupervisor(core, sessions)
    try:
        yield
    finally:
        await app.state.supervisor.close()
        await core.close()
        await engine.dispose()


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
    app.include_router(events.router)
    app.include_router(human.router)
    app.include_router(browser.router)
    app.include_router(artifacts.router)
    app.include_router(diagnostics.router)
    return app
