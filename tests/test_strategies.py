import dataclasses

import pytest

from src.core.contracts import Decision
from src.core.strategies import BUILTIN_STRATEGIES, MacdCross, RsiReversion, SataParity
from src.data.ohlc import CandleSeries

from conftest import SIGNAL_IDS


def test_registry_ids_and_versions_unique(registry):
    ids = registry.ids()
    assert len(ids) == len(set(ids)) == len(BUILTIN_STRATEGIES)
    for d in registry.catalog():
        assert d["version"] and d["strategy_id"]


def test_default_params_match_brief():
    p = MacdCross().params
    assert (p["fast"], p["slow"], p["signal"]) == (12, 26, 9)
    assert RsiReversion().params["period"] == 14


@pytest.mark.parametrize("cls,params", [
    (MacdCross, {"fast": 30, "slow": 20}),
    (MacdCross, {"fast": 0}),
    (MacdCross, {"unknown": 1}),
    (MacdCross, {"fast": True}),
    (RsiReversion, {"period": 14.5}),
    (RsiReversion, {"oversold": 80.0}),
])
def test_invalid_params_rejected(cls, params):
    with pytest.raises(ValueError):
        cls(**params)


def test_sata_parity_is_not_evaluable(series):
    assert SataParity.available is False and SataParity.unavailable_reason == "MQL5_SOURCE_MISSING"
    with pytest.raises(RuntimeError):
        SataParity().evaluate(series)


@pytest.mark.parametrize("sid", SIGNAL_IDS + ["atr_regime"])
def test_no_look_ahead_future_mutation(registry, series, sid):
    """Rewriting every candle after i must not change the decision at i."""
    strat = registry.get(sid)()
    c = list(series.candles)
    for i in range(120, 500, 37):
        base = strat.evaluate(series.upto(i))
        mutated = c[:i + 1] + [dataclasses.replace(x, open=x.open * 1.2, high=x.high * 1.3,
                                                   low=x.low * 0.7, close=x.close * 0.8) for x in c[i + 1:]]
        other = strat.evaluate(CandleSeries(series.provenance, tuple(mutated)).upto(i))
        assert base.to_dict() == other.to_dict()


@pytest.mark.parametrize("sid", SIGNAL_IDS)
def test_directional_results_carry_evidence_and_stop(registry, series, sid):
    strat = registry.get(sid)()
    seen = 0
    for i in range(100, len(series)):
        r = strat.evaluate(series.upto(i))
        if r.decision is not Decision.NO_TRADE:
            seen += 1
            assert r.evidence and r.stop_distance and r.stop_distance > 0
            assert all(e.candle_ts <= series.candles[i].ts for e in r.evidence)
    assert seen > 0, "fixture should exercise every signal strategy"


def test_warmup_returns_no_trade(registry, series):
    for sid in SIGNAL_IDS:
        r = registry.get(sid)().evaluate(series.upto(5))
        assert r.decision is Decision.NO_TRADE
