import json

import pytest

from src.core.events import EVENT_SCHEMA_VERSION, EventEnvelope, EventType


def sample_event(**overrides):
    values = {
        "event_id": "evt-0001",
        "event_type": EventType.MARKET_BAR_CLOSED,
        "occurred_at_ms": 1_797_000_000_000,
        "source": "mt5:test-broker:XAUUSD",
        "correlation_id": "run-0001",
        "payload": {
            "symbol": "XAUUSD",
            "instrument_type": "cfd",
            "timeframe": "M15",
            "bar_ts": 1_797_000_000,
            "closed": True,
        },
    }
    values.update(overrides)
    return EventEnvelope(**values)


def test_event_round_trip_is_canonical():
    event = sample_event()
    raw = json.loads(event.to_json())
    restored = EventEnvelope.from_dict(raw)
    assert restored == event
    assert restored.schema_version == EVENT_SCHEMA_VERSION
    assert restored.to_json() == event.to_json()


@pytest.mark.parametrize("field,value", [
    ("event_id", ""),
    ("source", " "),
    ("correlation_id", ""),
])
def test_required_identifiers_must_be_non_empty(field, value):
    with pytest.raises(ValueError):
        sample_event(**{field: value})


@pytest.mark.parametrize("timestamp", [-1, True, 1.5, "123"])
def test_timestamp_must_be_non_negative_integer_milliseconds(timestamp):
    with pytest.raises(ValueError):
        sample_event(occurred_at_ms=timestamp)


def test_unknown_event_type_is_rejected():
    raw = sample_event().to_dict()
    raw["event_type"] = "trade.execute"
    with pytest.raises(ValueError, match="unsupported event_type"):
        EventEnvelope.from_dict(raw)


def test_unknown_or_missing_fields_are_rejected():
    raw = sample_event().to_dict()
    raw["tenant_secret"] = "must-not-be-accepted"
    with pytest.raises(ValueError, match="unknown event fields"):
        EventEnvelope.from_dict(raw)

    raw = sample_event().to_dict()
    del raw["correlation_id"]
    with pytest.raises(ValueError, match="missing event fields"):
        EventEnvelope.from_dict(raw)


def test_live_execution_event_type_does_not_exist():
    assert "trade.execute" not in {event.value for event in EventType}
