"""Shared ATR-based stop/target proposal (proposal only, never an order)."""
from src.core.strategies.base import ParamSpec

ATR_PARAMS = (
    ParamSpec("atr_period", int, 14, 5, 50, "ATR period for stop proposal"),
    ParamSpec("stop_atr_mult", float, 1.5, 0.5, 5.0, "Stop distance in ATR"),
    ParamSpec("reward_risk", float, 1.5, 0.5, 5.0, "Target distance / stop distance"),
)


def atr_stop_target(strategy, series):
    a = strategy._atr_last(series, strategy.params["atr_period"])
    if a is None or a <= 0:
        return None, None
    stop = a * strategy.params["stop_atr_mult"]
    return round(stop, 4), round(stop * strategy.params["reward_risk"], 4)
