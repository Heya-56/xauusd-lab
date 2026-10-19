import json

import pytest

from src.core.event_bus import InProcessEventBus, JsonlEventLog, replay
from src.core.events import EventEnvelope, EventType


def make_event(event_id="evt-1", event_type=EventType.MARKET_BAR_CLOSED, payload=None):
    return EventEnvelope(
        event_id=event_id,
        event_type=event_type,
        occurred_at_ms=1_797_000_000_000,
        source="fixture",
        correlation_id="run-1",
        payload=payload if payload is not None else {"symbol": "XAUUSD", "closed": True},
    )


def test_bus_delivers_only_to_matching_subscribers_and_deduplicates():
    bus = InProcessEventBus()
    seen = []
    handler = seen.append
    bus.subscribe(EventType.MARKET_BAR_CLOSED, handler)
    bus.subscribe(EventType.MARKET_BAR_CLOSED, handler)
    bus.subscribe(EventType.SYSTEM_HEALTH, lambda event: seen.append("wrong"))
    event = make_event()

    assert bus.publish(event) == 1
    assert seen == [event]


def test_bus_rejects_invalid_inputs_and_propagates_handler_errors():
    bus = InProcessEventBus()
    with pytest.raises(ValueError):
        bus.subscribe("market.tick", lambda event: None)
    with pytest.raises(ValueError):
        bus.publish({"event_type": "market.tick"})

    def broken(_event):
        raise RuntimeError("consumer failed")

    bus.subscribe(EventType.MARKET_TICK, broken)
    with pytest.raises(RuntimeError, match="consumer failed"):
        bus.publish(make_event(event_type=EventType.MARKET_TICK))


def test_jsonl_log_appends_and_reads_events(tmp_path):
    log = JsonlEventLog(tmp_path / "nested" / "events.jsonl")
    first, second = make_event("evt-1"), make_event("evt-2", EventType.SYSTEM_HEALTH)
    log.append(first)
    log.append(second)

    assert log.read_all() == [first, second]
    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["schema_version"] == "1.0" for line in lines)


def test_missing_log_is_empty_and_malformed_log_fails_closed(tmp_path):
    log = JsonlEventLog(tmp_path / "missing.jsonl")
    assert log.read_all() == []

    log.path.write_text('{"event_type":"trade.execute"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid event log line 1"):
        log.read_all()


def test_blank_or_partial_log_line_fails_closed(tmp_path):
    log = JsonlEventLog(tmp_path / "events.jsonl")
    log.path.write_text("{}\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid event log line 1"):
        log.read_all()


def test_replay_preserves_order_and_does_not_invent_execution():
    bus = InProcessEventBus()
    seen = []
    bus.subscribe(EventType.MARKET_BAR_CLOSED, seen.append)
    events = [make_event("one"), make_event("two")]
    assert replay(events, bus) == 2
    assert [event.event_id for event in seen] == ["one", "two"]
    assert "trade.execute" not in {event.value for event in EventType}
