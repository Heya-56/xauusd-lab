import pytest

from src.core.registry import StrategyRegistry, validate_config
from src.data.adapters import SyntheticFixtureAdapter

SIGNAL_IDS = ["macd_cross", "rsi_reversion", "ema_trend", "fibonacci_pullback", "sr_breakout", "ema_slope_distance"]


@pytest.fixture(scope="session")
def series():
    return SyntheticFixtureAdapter().load()


@pytest.fixture(scope="session")
def registry():
    return StrategyRegistry()


def cfg(registry, *ids, profile="intraday", params=None):
    params = params or {}
    return validate_config({"profile": profile, "strategies": {
        i: {"enabled": True, "params": params.get(i, {})} for i in ids}}, registry)
