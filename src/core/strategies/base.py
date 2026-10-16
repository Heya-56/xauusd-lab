"""Common interface for every switchable strategy.

A strategy is identified by (strategy_id, version). Parameters are declared
with validated ranges; the dashboard can only choose values inside them.
`evaluate()` receives a series that already ends at the decision candle, so it
structurally cannot read future candles. It must return a StrategyResult with
evidence; BUY/SELL without evidence is rejected by the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.contracts import Decision, Evidence, StrategyResult
from src.core.indicators import atr
from src.data.ohlc import CandleSeries


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: type
    default: Any
    minimum: float
    maximum: float
    description: str = ""

    def validate(self, value: Any) -> Any:
        if self.kind is int and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"{self.name}: expected int")
        if self.kind is float and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError(f"{self.name}: expected number")
        if not (self.minimum <= value <= self.maximum):
            raise ValueError(f"{self.name}: {value} outside [{self.minimum}, {self.maximum}]")
        return self.kind(value)

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.kind.__name__, "default": self.default,
                "min": self.minimum, "max": self.maximum, "description": self.description}


class Strategy:
    strategy_id: str = "abstract"
    version: str = "0.0.0"
    name: str = "Abstract"
    description: str = ""
    role: str = "signal"            # "signal" proposes BUY/SELL, "filter" can only block
    available: bool = True          # False => registered but never evaluated
    unavailable_reason: str = ""
    timeframes: tuple[str, ...] = ("M5", "M15", "H1", "H4", "D1")
    param_specs: tuple[ParamSpec, ...] = ()

    def __init__(self, **params: Any):
        self.params = self.validate_params(params)

    @classmethod
    def validate_params(cls, params: dict) -> dict:
        known = {p.name: p for p in cls.param_specs}
        unknown = set(params) - set(known)
        if unknown:
            raise ValueError(f"{cls.strategy_id}: unknown params {sorted(unknown)}")
        out = {}
        for name, spec in known.items():
            out[name] = spec.validate(params.get(name, spec.default))
        cls.check_relations(out)
        return out

    @classmethod
    def check_relations(cls, params: dict) -> None:
        """Override for cross-parameter constraints (e.g. fast < slow)."""

    def warmup(self) -> int:
        return 50

    def evaluate(self, series: CandleSeries) -> StrategyResult:  # pragma: no cover
        raise NotImplementedError

    # ---- helpers -------------------------------------------------------
    def _result(self, decision: Decision, series: CandleSeries, evidence=(), codes=(),
                stop=None, target=None, invalidation=None) -> StrategyResult:
        return StrategyResult(self.strategy_id, self.version, dict(self.params), decision,
                              series.last_ts or 0, tuple(evidence), tuple(codes),
                              invalidation, stop, target)

    def _ev(self, name: str, value: Any, ts: int, kind: str = "indicator") -> Evidence:
        v = round(value, 6) if isinstance(value, float) else value
        return Evidence(kind, name, v, ts, self.strategy_id)

    def _no_trade(self, series: CandleSeries, code: str) -> StrategyResult:
        return self._result(Decision.NO_TRADE, series, codes=(code,))

    @staticmethod
    def _atr_last(series: CandleSeries, n: int = 14) -> float | None:
        c = series.candles
        vals = atr([x.high for x in c], [x.low for x in c], [x.close for x in c], n)
        return vals[-1] if vals else None

    @classmethod
    def describe(cls) -> dict:
        return {"strategy_id": cls.strategy_id, "version": cls.version, "name": cls.name,
                "description": cls.description, "role": cls.role, "available": cls.available,
                "unavailable_reason": cls.unavailable_reason, "timeframes": list(cls.timeframes),
                "params": [p.to_dict() for p in cls.param_specs]}
