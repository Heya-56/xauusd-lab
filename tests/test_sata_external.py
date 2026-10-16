"""S.A.T.A. external candidate: fail closed when absent; real behaviour when installed."""
import importlib
import os
import random

import pytest

from src.core.registry import ConfigError, StrategyRegistry, validate_config


def test_disabled_by_default_cannot_be_enabled(registry):
    from src.core.strategies.sata_external import SataExternal
    if os.environ.get("HINOVA_ENABLE_SATA") == "1":
        pytest.skip("explicitly enabled in this environment")
    assert SataExternal.available is False
    assert SataExternal.unavailable_reason in ("LICENSE_PENDING_SATA_DISABLED", "SATA_NOT_INSTALLED")
    with pytest.raises(ConfigError, match="unavailable"):
        validate_config({"profile": "intraday", "strategies": {"sata_external": {"enabled": True}}}, registry)


def test_no_sata_code_vendored():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert not (root / "sata").exists() and not (root / "src" / "sata").exists()


@pytest.fixture
def sata_enabled(monkeypatch):
    monkeypatch.setenv("HINOVA_ENABLE_SATA", "1")
    try:
        importlib.import_module("sata.strategies")
    except Exception:
        pytest.skip("S.A.T.A. package not installed (expected in CI)")
    import src.core.strategies.sata_external as mod
    mod = importlib.reload(mod)
    yield mod
    monkeypatch.delenv("HINOVA_ENABLE_SATA")
    importlib.reload(mod)


def _m15_series(n, seed=11):
    from src.core.contracts import InstrumentType
    from src.data.ohlc import Candle, CandleSeries, Provenance
    rng, p, cs = random.Random(seed), 2400.0, []
    for i in range(n):
        o = p
        p = max(1.0, p * (1 + rng.gauss(0.00004, 0.0012)))
        cs.append(Candle(1_767_225_600 + i * 900, round(o, 2), round(max(o, p) + 0.3, 2), round(min(o, p) - 0.3, 2), round(p, 2)))
    return CandleSeries(Provenance("XAUUSD", InstrumentType.SYNTHETIC, "M15", "fixture"), tuple(cs))


def test_sata_runs_without_look_ahead_when_installed(sata_enabled):
    import dataclasses
    from src.data.ohlc import CandleSeries
    strat = sata_enabled.SataExternal(horizon=1, method=0, min_score=50)
    s = _m15_series(strat.warmup() + 60)
    seen = set()
    for i in range(strat.warmup() + 5, len(s), 11):
        a = strat.evaluate(s.upto(i))
        mutated = list(s.candles[:i + 1]) + [dataclasses.replace(c, close=c.close * 1.5, high=c.high * 1.5)
                                             for c in s.candles[i + 1:]]
        b = strat.evaluate(CandleSeries(s.provenance, tuple(mutated)).upto(i))
        assert a.to_dict() == b.to_dict()
        seen.add(a.decision.value)
        if a.decision.value != "NO_TRADE":
            assert a.stop_distance > 0 and a.evidence
    assert seen                                         # evaluated without error


def test_sata_timeframe_mismatch_is_no_trade(sata_enabled):
    strat = sata_enabled.SataExternal(horizon=2)        # swing needs H1 trigger
    r = strat.evaluate(_m15_series(50))
    assert r.decision.value == "NO_TRADE" and r.rationale_codes[0].startswith("TIMEFRAME_MISMATCH")
