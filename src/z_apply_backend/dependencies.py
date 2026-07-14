from __future__ import annotations

from typing import cast

from fastapi import Request
from z_apply_core.integrations import ZApplyCore

from z_apply_backend.services.event_hub import EventHub
from z_apply_backend.services.run_supervisor import RunSupervisor


def core(request: Request) -> ZApplyCore:
    return cast(ZApplyCore, request.app.state.core)


def supervisor(request: Request) -> RunSupervisor:
    return cast(RunSupervisor, request.app.state.supervisor)


def event_hub(request: Request) -> EventHub:
    return cast(EventHub, request.app.state.event_hub)
