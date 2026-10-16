import dataclasses

import pytest

from src.core.backtest import metrics, run_backtest
from src.core.registry import load_profiles
from src.core.walkforward import walk_forward
from src.data.ohlc import CandleSeries

PROFILES = load_profiles()
GRID = {"sr_breakout": {"lookback": [10, 20, 40]}}


def wf(series, registry, **kw):
    return walk_forward(series, registry, PROFILES, "intraday", ["sr_breakout"], train_bars=240,
                        test_bars=90, allow_synthetic=True, min_train_trades=3, **kw)


def test_folds_are_chronological_and_test_windows_disjoint(series, registry):
    r = wf(series, registry)
    assert len(r.folds) == 4
    for a, b in zip(r.folds, r.folds[1:]):
        assert a.train_start_ts < a.test_start_ts <= a.test_end_ts < b.test_start_ts


def test_oos_entries_only_inside_test_windows(series, registry):
    r = wf(series, registry, grid=GRID)
    windows = [(f.test_start_ts, f.test_end_ts) for f in r.folds]
    assert r.oos_trades
    for t in r.oos_trades:
        assert any(a <= t.signal_ts <= b for a, b in windows)


def test_parameter_choice_never_sees_the_future(series, registry):
    base = wf(series, registry, grid=GRID)
    f0 = base.folds[0]
    cut = next(i for i, c in enumerate(series.candles) if c.ts == f0.test_start_ts)
    mutated = list(series.candles[:cut]) + [dataclasses.replace(c, open=c.open * 1.3, high=c.high * 1.4,
                                                                low=c.low * 0.8, close=c.close * 0.9)
                                            for c in series.candles[cut:]]
    other = wf(CandleSeries(series.provenance, tuple(mutated)), registry, grid=GRID)
    assert other.folds[0].params == f0.params and other.folds[0].train == f0.train


def test_grid_picks_best_train_expectancy(series, registry):
    r = wf(series, registry, grid=GRID)
    f0 = r.folds[0]
    from src.core.registry import validate_config
    cut = next(i for i, c in enumerate(series.candles) if c.ts == f0.test_start_ts)
    scores = {}
    for lb in GRID["sr_breakout"]["lookback"]:
        cfg = validate_config({"profile": "intraday", "strategies": {"sr_breakout": {"enabled": True,
                               "params": {"lookback": lb}}}}, registry, PROFILES)
        m = metrics(run_backtest(series.upto(cut - 1), cfg, registry, allow_synthetic=True, start_index=0, end_index=cut))
        if m["trades"] >= 3:
            scores[lb] = m["expectancy_r"]
    assert f0.params["sr_breakout"]["lookback"] == max(scores, key=scores.get)


def test_deterministic_and_split_shape(series, registry):
    a, b = wf(series, registry, grid=GRID), wf(series, registry, grid=GRID)
    assert a.to_dict() == b.to_dict()
    s = a.split(len(series))
    assert set(s) >= {"in_sample", "out_of_sample", "all"}
    assert s["out_of_sample"]["trades"] == len(a.oos_trades)


def test_invalid_combinations_skipped_and_bad_sizes_rejected(series, registry):
    r = walk_forward(series, registry, PROFILES, "intraday", ["ema_trend"], train_bars=240, test_bars=90,
                     allow_synthetic=True, grid={"ema_trend": {"fast": [20, 60], "slow": [50]}}, min_train_trades=1)
    assert all(f.params["ema_trend"]["fast"] < f.params["ema_trend"]["slow"] for f in r.folds)
    with pytest.raises(ValueError):
        walk_forward(series, registry, PROFILES, "intraday", ["sr_breakout"], train_bars=10, test_bars=5)


def test_oversized_grid_refused(series, registry):
    big = {"macd_cross": {"fast": [5, 6, 7, 8, 9], "slow": [20, 21, 22, 23, 24]}}
    with pytest.raises(ValueError, match="max_combos"):
        walk_forward(series, registry, PROFILES, "intraday", ["macd_cross"], train_bars=240, test_bars=90, grid=big)
