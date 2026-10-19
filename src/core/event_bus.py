"""Minimal in-process event dispatch and append-only JSONL research log.

The bus is deliberately synchronous and transport-neutral. It does not create
threads, sockets, broker sessions, or orders. Handler failures propagate to
the caller so a failed consumer is never silently reported as successful.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

from src.core.events import EventEnvelope, EventType


EventHandler = Callable[[EventEnvelope], None]


class InProcessEventBus:
    """Deterministic, synchronous dispatcher for a single process."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        if not isinstance(event_type, EventType):
            raise ValueError("event_type must be an EventType")
        if not callable(handler):
            raise ValueError("handler must be callable")
        handlers = self._handlers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def publish(self, event: EventEnvelope) -> int:
        """Deliver to a snapshot of subscribers; return number of handlers called."""
        if not isinstance(event, EventEnvelope):
            raise ValueError("event must be an EventEnvelope")
        handlers = tuple(self._handlers.get(event.event_type, ()))
        for handler in handlers:
            handler(event)
        return len(handlers)


class JsonlEventLog:
    """Append-only JSONL log for research events; no network or broker I/O."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, event: EventEnvelope) -> None:
        if not isinstance(event, EventEnvelope):
            raise ValueError("event must be an EventEnvelope")
        line = event.to_json()
        # Ensure the payload can be serialized before opening the file.
        json.loads(line)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")

    def read_all(self) -> list[EventEnvelope]:
        """Read the log strictly; malformed or partial lines raise ValueError."""
        if not self.path.exists():
            return []
        events: list[EventEnvelope] = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    raise ValueError(f"blank event log line at {line_number}")
                try:
                    raw = json.loads(line)
                    events.append(EventEnvelope.from_dict(raw))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid event log line {line_number}: {exc}") from exc
        return events


def replay(events: Iterable[EventEnvelope], bus: InProcessEventBus) -> int:
    """Replay known events in order through the same synchronous dispatcher."""
    count = 0
    for event in events:
        bus.publish(event)
        count += 1
    return count
