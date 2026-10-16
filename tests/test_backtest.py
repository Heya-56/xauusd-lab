import pytest

from src.core.backtest import metrics, run_backtest, split_metrics

from conftest import cfg

# Golden values on the deterministic SYNTHETIC fixture (seed 7). They detect
# behavioural regressions; they say nothing about real-market performance.
GOLDEN = {"macd_cross": (15, 4.0912), "rsi_reversion": (9, 30.8978), "ema_trend": (7, 30.0062),
          "fibonacci_pullback": (12, -1.6307), "sr_breakout": (19, 9.877)}


def test_fixture_hash_is_stable(series):
    assert series.data_hash() == "f11f8032061c3eb0f5d04aa8"


@pytest.mark.parametrize("sid", list(GOLDEN))
def test_golden_regression(series, registry, sid):
    trades = run_backtest(series, cfg(registry, sid), registry, allow_synthetic=True)
    m = metrics(trades, len(series))
    assert (m["trades"], m["net_points"]) == GOLDEN[sid]


def test_reproducible_and_costs_applied(series, registry):
    c = cfg(registry, "sr_breakout")
    a = run_backtest(series, c, registry, allow_synthetic=True)
    b = run_backtest(series, c, registry, allow_synthetic=True)
    assert a == b
    costs = c.profile["costs"]
    for t in a:
        assert t.cost == pytest.approx(costs["spread"] + 2 * costs["slippage"] + costs["commission"])
        assert t.entry_ts > t.signal_ts                       # entry strictly after the decision candle
        assert t.exit_ts >= t.entry_ts


def test_entry_is_next_open_plus_costs(series, registry):
    c = cfg(registry, "sr_breakout")
    t = run_backtest(series, c, registry, allow_synthetic=True)[0]
    idx = {x.ts: x for x in series.candles}
    sgn = 1 if t.side == "BUY" else -1
    expected = idx[t.entry_ts].open + sgn * (c.profile["costs"]["spread"] / 2 + c.profile["costs"]["slippage"])
    assert t.entry == pytest.approx(round(expected, 4))


def test_synthetic_needs_explicit_flag(series, registry):
    assert run_backtest(series, cfg(registry, "sr_breakout"), registry) == []


def test_split_and_empty_metrics(series, registry):
    trades = run_backtest(series, cfg(registry, "sr_breakout"), registry, allow_synthetic=True)
    s = split_metrics(trades, series)
    assert s["in_sample"]["trades"] + s["out_of_sample"]["trades"] == len(trades)
    assert metrics([])["sample_warning"] == "NO_TRADES"
    assert s["all"]["sample_warning"] == "BELOW_30_TRADES"


def test_daily_research_never_fabricates_without_data(tmp_path):
    from research.daily_research import run
    res = run("real", tmp_path / "empty", tmp_path / "out", None)
    assert res["meta"]["status"] == "DATA_MISSING" and res["rows"] == []
    assert (tmp_path / "out" / "report.md").read_text().count("DATA_MISSING") >= 1


def test_daily_research_excludes_futures(tmp_path, series):
    import json as _j
    d = tmp_path / "data"
    d.mkdir()
    (d / "gc.csv").write_text("ts,open,high,low,close\n" + "\n".join(
        f"{c.ts},{c.open},{c.high},{c.low},{c.close}" for c in series.candles))
    (d / "gc.csv.meta.json").write_text(_j.dumps({"symbol": "XAUUSD", "instrument_type": "futures",
                                                  "timeframe": "M15", "source": "yahoo:GC=F"}))
    from research.daily_research import run
    res = run("real", d, tmp_path / "out", None)
    assert res["meta"]["status"] == "DATA_MISSING"
    assert any("excluded" in n for n in res["meta"]["data_notes"])


def test_daily_research_fixture_matches_locked_baseline(tmp_path):
    from pathlib import Path
    from research.daily_research import run
    base = Path(__file__).resolve().parents[1] / "reports/baseline/fixture_baseline.json"
    res = run("fixture", tmp_path, tmp_path / "out", base)
    assert res["regressions"] == []
