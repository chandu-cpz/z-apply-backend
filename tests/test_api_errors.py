from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from z_apply_core.integrations import (
    BrowserControlConflict,
    BrowserUnavailable,
    HumanRequestAlreadyResolved,
    RunNotFound,
)

from z_apply_backend.api.errors import integration_error
from z_apply_backend.api.human import _live_request_id


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    [
        (RunNotFound(), 404, "run_not_found"),
        (BrowserUnavailable(), 409, "browser_unavailable"),
        (BrowserControlConflict(), 409, "browser_control_conflict"),
        (HumanRequestAlreadyResolved(), 409, "human_request_already_resolved"),
        (RuntimeError(), 500, "integration_failure"),
    ],
)
def test_public_integration_errors_have_stable_transport_codes(
    exception: Exception, status: int, code: str
) -> None:
    error = integration_error(exception)

    assert error.status_code == status
    assert error.detail == {"code": code}


@pytest.mark.asyncio
async def test_live_human_request_preserves_cores_opaque_id() -> None:
    class Handle:
        async def human_requests(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(request_id="d11ba67d0bd34cc2a679e01407d73dda")]

    canonical = UUID("d11ba67d-0bd3-4cc2-a679-e01407d73dda")

    assert await _live_request_id(Handle(), canonical) == "d11ba67d0bd34cc2a679e01407d73dda"  # type: ignore[arg-type]
