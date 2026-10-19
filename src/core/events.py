"""Versioned event envelope for the headless XAUUSD Lab.

This module is stdlib-only and transport-agnostic. It defines the contract
between adapters, the deterministic engine, risk checks and research reporting.
It does not open sockets, publish messages or execute orders.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

EVENT_SCHEMA_VERSION = "1.0"


class EventType(str, Enum):
    MARKET_TICK = "market.tick"
    MARKET_BAR_CLOSED = "market.bar_closed"
    STRATEGY_SIGNAL = "strategy.signal"
    RISK_DECISION = "risk.decision"
    RESEARCH_RESULT = "research.result"
    SYSTEM_HEALTH = "system.health"


@dataclass(frozen=True)
class EventEnvelope:
    """Immutable, serializable envelope shared across headless components.

    Timestamps are UTC Unix epoch milliseconds. The payload must contain
    validated domain data; the envelope does not interpret it as a decision.
    """

    event_id: str
    event_type: EventType
    occurred_at_ms: int
    source: str
    correlation_id: str
    payload: dict[str, Any]
    schema_version: str = EVENT_SCHEMA_VERSION
    causation_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("event_id", "source", "correlation_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.event_type, EventType):
            raise ValueError("event_type must be an EventType")
        if isinstance(self.occurred_at_ms, bool) or not isinstance(self.occurred_at_ms, int):
            raise ValueError("occurred_at_ms must be an integer UTC epoch in milliseconds")
        if self.occurred_at_ms < 0:
            raise ValueError("occurred_at_ms must be non-negative")
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported event schema version: {self.schema_version}")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be an object")
        if self.causation_id is not None and (
            not isinstance(self.causation_id, str) or not self.causation_id.strip()
        ):
            raise ValueError("causation_id must be None or a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "occurred_at_ms": self.occurred_at_ms,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        """Canonical JSON for logs, fixtures and future transport adapters."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EventEnvelope":
        if not isinstance(raw, dict):
            raise ValueError("event envelope must be an object")
        required = {
            "schema_version", "event_id", "event_type", "occurred_at_ms",
            "source", "correlation_id", "payload",
        }
        missing = required - set(raw)
        unknown = set(raw) - (required | {"causation_id"})
        if missing:
            raise ValueError(f"missing event fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"unknown event fields: {sorted(unknown)}")
        try:
            event_type = EventType(raw["event_type"])
        except (ValueError, TypeError):
            raise ValueError(f"unsupported event_type: {raw.get('event_type')!r}") from None
        return cls(
            event_id=raw["event_id"],
            event_type=event_type,
            occurred_at_ms=raw["occurred_at_ms"],
            source=raw["source"],
            correlation_id=raw["correlation_id"],
            payload=raw["payload"],
            schema_version=raw["schema_version"],
            causation_id=raw.get("causation_id"),
        )
