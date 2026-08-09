from __future__ import annotations

from datetime import UTC, datetime

from z_apply_core.integrations.models import CoreEvent

from z_apply_backend.persistence.repositories import _model_call_values


def _metrics_event() -> CoreEvent:
    return CoreEvent(
        run_id="d48c2b30-01a0-418b-baf8-6a3ccde5608f",
        sequence=42,
        occurred_at=datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC),
        type="model.call.metrics",
        source={"component": "graph", "agent": "researcher"},
        level="info",
        payload={
            "role": "researcher",
            "model_id": "deepseek/v3",
            "provider": "nim",
            "input_tokens": 1200,
            "output_tokens": 340,
            "cache_read_tokens": 800,
            "ttft_ms": 180,
            "duration_ms": 15200,
            "tok_per_second": 22.4,
            "cost_usd": 0.001234,
        },
    )


def test_model_call_values_maps_ledger_event_to_row() -> None:
    values = _model_call_values(_metrics_event())

    assert values["run_id"].hex == "d48c2b3001a0418bbaf86a3ccde5608f"
    assert values["sequence"] == 42
    assert values["agent"] == "researcher"
    assert values["model"] == "deepseek/v3"
    assert values["provider"] == "nim"
    assert values["input_tokens"] == 1200
    assert values["output_tokens"] == 340
    assert values["cache_read_tokens"] == 800
    assert values["ttft_ms"] == 180
    assert values["duration_ms"] == 15200
    assert values["tok_per_second"] == 22.4
    assert values["cost_usd"] == 0.001234
    assert values["occurred_at"] == datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


def test_model_call_values_handles_missing_fields() -> None:
    event = _metrics_event()
    event = CoreEvent(
        run_id=event.run_id,
        sequence=event.sequence,
        occurred_at=event.occurred_at,
        type=event.type,
        source=event.source,
        level=event.level,
        payload={"role": "orchestrator"},
    )
    values = _model_call_values(event)

    assert values["model"] == ""
    assert values["provider"] == ""
    assert values["input_tokens"] == 0
    assert values["output_tokens"] == 0
    assert values["cache_read_tokens"] == 0
    assert values["ttft_ms"] is None
    assert values["tok_per_second"] is None
    assert values["cost_usd"] is None
