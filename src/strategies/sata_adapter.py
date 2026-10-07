"""Bridge S.A.T.A. -> XAUUSD Lab.

S.A.T.A. remains the source of strategy logic. The Lab wraps it behind a stable
research interface so every S.A.T.A. configuration can be benchmarked like any
other candidate strategy.

No ML/AI is used here.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from importlib import import_module
from typing import Any

SATA_METHODS = ("tendance", "smc", "orderblock", "combine")
SATA_HORIZONS = ("scalping", "normal", "swing")

@dataclass(frozen=True)
class StrategyCandidate:
    id: str
    source: str
    horizon: str
    method: str
    bias_tf: str
    setup_tf: str
    trigger_tf: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

CATALOG = [
    StrategyCandidate(
        f"sata-{h}-{m}", "sata", h, m,
        {"scalping": "M15", "normal": "H4", "swing": "D1"}[h],
        {"scalping": "M5", "normal": "H1", "swing": "H4"}[h],
        {"scalping": "M1", "normal": "M15", "swing": "H1"}[h],
        f"S.A.T.A. {h} / {m}",
    )
    for h in SATA_HORIZONS for m in SATA_METHODS
]

def catalog() -> list[dict[str, Any]]:
    return [c.to_dict() for c in CATALOG]

def load_sata_strategies() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        mod = import_module("sata.strategies")
    except ImportError as exc:
        raise RuntimeError(
            "S.A.T.A. package not installed. Keep the Lab in research-only "
            "mode until the S.A.T.A. source is vendored/installed."
        ) from exc
    strategies = getattr(mod, "STRATEGIES", None)
    methods = getattr(mod, "METHODS", None)
    if not isinstance(strategies, dict) or not isinstance(methods, dict):
        raise RuntimeError("Invalid S.A.T.A. strategy registry.")
    return strategies, methods

def analyze_with_sata(symbol: str, data: dict[str, list[Any]],
                      horizon: str, method: str) -> Any:
    if horizon not in SATA_HORIZONS:
        raise ValueError(f"Unknown S.A.T.A. horizon: {horizon}")
    if method not in SATA_METHODS:
        raise ValueError(f"Unknown S.A.T.A. method: {method}")
    strategies, _ = load_sata_strategies()
    try:
        spec = strategies[horizon]
    except KeyError as exc:
        raise RuntimeError(f"S.A.T.A. strategy '{horizon}' is unavailable") from exc
    mod = import_module("sata.strategies")
    analyze = getattr(mod, "analyze", None)
    if not callable(analyze):
        raise RuntimeError("S.A.T.A. analyzer is unavailable")
    return analyze(symbol, data, spec, method)
