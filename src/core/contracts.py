"""Versioned domain contracts for Hinova Trading Lab.

Pure standard library. No I/O, no network, no LLM. Every other layer
(data, API, agents, dashboard) exchanges these shapes, never free-form prose.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

SIGNAL_SCHEMA_VERSION = "1.0"
OHLC_SCHEMA_VERSION = "1.0"


class Decision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TRADE = "NO_TRADE"


class DataStatus(str, Enum):
    VALID = "valid"
    STALE = "stale"
    INVALID = "invalid"
    MISSING = "missing"


class InstrumentType(str, Enum):
    """Spot/CFD and futures are distinct identities and are never interchanged."""
    SPOT = "spot"
    CFD = "cfd"
    FUTURES = "futures"
    SYNTHETIC = "synthetic_fixture"


class Mode(str, Enum):
    RESEARCH = "research"
    PAPER = "paper"
    LIVE_DISABLED = "live_disabled"


TIMEFRAME_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


@dataclass(frozen=True)
class Evidence:
    """A verifiable fact produced by deterministic code.

    `evidence_id` is a content hash, so an agent can only cite evidence that
    exists in the record; it cannot invent an identifier that validates.
    """
    kind: str                 # e.g. "indicator", "candle", "pivot", "rule"
    name: str                 # e.g. "macd_line"
    value: Any
    candle_ts: int            # epoch seconds (UTC) of the closed candle used
    strategy_id: str

    @property
    def evidence_id(self) -> str:
        return content_hash({"k": self.kind, "n": self.name, "v": self.value,
                             "t": self.candle_ts, "s": self.strategy_id})[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_id"] = self.evidence_id
        return d


@dataclass(frozen=True)
class StrategyResult:
    strategy_id: str
    strategy_version: str
    params: dict
    decision: Decision
    as_of_ts: int
    evidence: tuple[Evidence, ...] = ()
    rationale_codes: tuple[str, ...] = ()
    invalidation: str | None = None
    stop_distance: float | None = None     # price units, proposal only
    target_distance: float | None = None   # price units, proposal only

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "params": dict(self.params),
            "decision": self.decision.value,
            "as_of_ts": self.as_of_ts,
            "evidence": [e.to_dict() for e in self.evidence],
            "rationale_codes": list(self.rationale_codes),
            "invalidation": self.invalidation,
            "stop_distance": self.stop_distance,
            "target_distance": self.target_distance,
        }


@dataclass
class RiskResult:
    allowed: bool
    veto_codes: list[str] = field(default_factory=list)
    execution_allowed: bool = False  # never True in this milestone

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SignalRecord:
    """Full, reproducible decision record (what the API returns)."""
    schema_version: str
    symbol: str
    instrument_type: str
    source: str
    profile: str
    timeframe: str
    decision: Decision
    data_status: DataStatus
    as_of_ts: int
    strategy_results: list[StrategyResult]
    risk: RiskResult
    reason_codes: list[str]
    config_hash: str
    data_hash: str
    mode: str = Mode.RESEARCH.value
    agent_review: dict | None = None

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "instrument_type": self.instrument_type,
            "source": self.source,
            "profile": self.profile,
            "timeframe": self.timeframe,
            "decision": self.decision.value,
            "data_status": self.data_status.value,
            "as_of_ts": self.as_of_ts,
            "strategy_ids": [r.strategy_id for r in self.strategy_results],
            "strategy_results": [r.to_dict() for r in self.strategy_results],
            "risk_status": "allowed" if self.risk.allowed else "blocked",
            "execution_allowed": self.risk.execution_allowed,
            "veto_codes": list(self.risk.veto_codes),
            "reason_codes": list(self.reason_codes),
            "config_hash": self.config_hash,
            "data_hash": self.data_hash,
            "mode": self.mode,
            "agent_review": self.agent_review,
        }

    def evidence_ids(self) -> set[str]:
        return {e.evidence_id for r in self.strategy_results for e in r.evidence}


def content_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()
