from src.gauge import evaluate, gauge, label
from tests.conftest import make_candles


def test_gauge_on_history():
    bars = make_candles(1500)
    r = evaluate(bars, 12)
    assert r["ready"] and -100 <= r["score"] <= 100 and len(r["votes"]) == 7
    assert r["sample"] > 0 and r["prob_up"] + r["prob_down"] <= 100
    assert label(80) == "ACHAT FORT" and label(0) == "NEUTRE" and label(-30) == "VENTE"


def test_uptrend_reads_buy():
    bars = [{"ts": i, "open": 100 + i * .5, "high": 101 + i * .5, "low": 99.5 + i * .5, "close": 100.4 + i * .5} for i in range(300)]
    assert evaluate(bars, 12)["score"] > 50


def test_not_ready_and_errors():
    assert evaluate(make_candles(20), 12)["ready"] is False
    out = gauge(lambda s: (_ for _ in ()).throw(RuntimeError("QuestDB")))
    assert all(not h["ready"] for h in out["horizons"])


def test_bar_lines():
    from src.feeders.mt5_history import bar_lines
    l = bar_lines("GOLD", 300, [{"time": 1767607200, "open": 1, "high": 2, "low": .5, "close": 1.5, "tick_volume": 10, "spread": 20}], .01)
    assert l == "bars,symbol=GOLD,tf=300s open=1.0,high=2.0,low=0.5,close=1.5,volume=10.0,ticks=10i,spread=0.2 1767607200000000000\n"
