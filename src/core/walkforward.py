"""Walk-forward validation (rolling, anchored on time order).

For each fold k:
    train window  [t0_k, t0_k + train)        -> optional parameter selection ONLY here
    test window   [t0_k + train, + test)      -> trades scored out-of-sample
    next fold starts `step` bars later (default = test, so test windows never overlap)

The stitched out-of-sample (OOS) trades of all test windows are what the score uses.
Entries happen only inside a test window; exits may finish in the following bars (as in
live trading). Candles before a test window are used as indicator history only.

Parameter selection (optional `grid`) is a deterministic arg-max of train expectancy in R
among combinations with at least `min_train_trades`; ties keep grid order. Without a grid
the defaults are used and the walk-forward measures stability across periods.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from src.core.backtest import Trade, metrics, run_backtest
from src.core.registry import ConfigError, StrategyRegistry, ValidatedConfig, validate_config
from src.data.ohlc import CandleSeries


@dataclass
class Fold:
    index: int
    train_start_ts: int
    test_start_ts: int
    test_end_ts: int
    params: dict
    train: dict
    test: dict


@dataclass
class WalkForwardResult:
    profile: str
    strategies: list[str]
    folds: list[Fold] = field(default_factory=list)
    oos_trades: list[Trade] = field(default_factory=list)
    train_trades: list[Trade] = field(default_factory=list)

    def split(self, total_bars: int) -> dict:
        """Same shape as backtest.split_metrics() so scoring.score_strategy can consume it."""
        return {"split_ts": None, "oos_fraction": None,
                "in_sample": metrics(self.train_trades, None),
                "out_of_sample": metrics(self.oos_trades, None),
                "all": metrics(self.oos_trades, total_bars)}

    def to_dict(self) -> dict:
        return {"profile": self.profile, "strategies": self.strategies,
                "folds": [f.__dict__ for f in self.folds],
                "oos": metrics(self.oos_trades, None), "train": metrics(self.train_trades, None)}


def _combos(grid: dict | None):
    """Yield {strategy_id: {param: value}} combinations in deterministic order."""
    if not grid:
        yield {}
        return
    keys = [(sid, p) for sid in sorted(grid) for p in sorted(grid[sid])]
    for values in itertools.product(*[grid[sid][p] for sid, p in keys]):
        combo: dict = {}
        for (sid, p), v in zip(keys, values):
            combo.setdefault(sid, {})[p] = v
        yield combo


def _config(registry, profiles, profile, strategy_ids, combo) -> ValidatedConfig | None:
    raw = {"profile": profile, "strategies": {sid: {"enabled": True, "params": combo.get(sid, {})}
                                              for sid in strategy_ids}}
    try:
        return validate_config(raw, registry, profiles)
    except ConfigError:
        return None                                   # invalid combination (e.g. fast >= slow) is skipped


def walk_forward(series: CandleSeries, registry: StrategyRegistry, profiles: dict, profile: str,
                 strategy_ids: list[str], *, train_bars: int, test_bars: int, step: int | None = None,
                 grid: dict | None = None, min_train_trades: int = 10,
                 allow_synthetic: bool = False, max_combos: int = 16) -> WalkForwardResult:
    if train_bars < 50 or test_bars < 10:
        raise ValueError("train_bars >= 50 and test_bars >= 10 required")
    step = step or test_bars
    n = len(series)
    res = WalkForwardResult(profile, list(strategy_ids))
    combos = list(_combos(grid))
    if len(combos) > max_combos:
        raise ValueError(f"grid has {len(combos)} combinations > max_combos={max_combos} (multiple-testing risk)")
    k, start = 0, 0
    while start + train_bars + test_bars <= n:
        tr0, te0, te1 = start, start + train_bars, start + train_bars + test_bars
        best, best_cfg, best_train = None, None, []
        for combo in combos:
            cfg = _config(registry, profiles, profile, strategy_ids, combo)
            if cfg is None:
                continue
            # train window only: no candle at or after te0 is visible
            trades = run_backtest(series.upto(te0 - 1), cfg, registry, allow_synthetic=allow_synthetic,
                                  start_index=tr0, end_index=te0)
            m = metrics(trades)
            key = m["expectancy_r"] if (m["trades"] >= min_train_trades and m["expectancy_r"] is not None) else None
            if best_cfg is None or (key is not None and (best is None or key > best)):
                best, best_cfg, best_train = key, cfg, trades
            if not grid:
                break
        if best_cfg is None:
            break
        test_trades = run_backtest(series, best_cfg, registry, allow_synthetic=allow_synthetic,
                                   start_index=te0, end_index=te1)
        c = series.candles
        res.folds.append(Fold(k, c[tr0].ts, c[te0].ts, c[te1 - 1].ts, best_cfg.strategies,
                              metrics(best_train), metrics(test_trades)))
        res.train_trades += best_train
        res.oos_trades += test_trades
        k += 1
        start += step
    return res
