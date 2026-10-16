"""Bar-by-bar backtester sharing the live engine path (no separate logic).

Timing (explicit, no look-ahead):
  * decision on the CLOSE of bar i, using only candles <= i
  * entry at the OPEN of bar i+1, worsened by half-spread + slippage
  * stop/target checked from bar i+1; if both touched in one bar -> STOP (conservative)
  * time exit at the close of bar entry+max_holding_bars
  * commission charged per round trip, in price units
Results are in price points per unit (no position sizing: sizing requires
broker contract metadata that is not available in the research core).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from src.core.contracts import Decision
from src.core.engine import evaluate
from src.core.registry import StrategyRegistry, ValidatedConfig
from src.core.risk_gate import AccountState
from src.data.ohlc import CandleSeries

LOOKBACK = 400


@dataclass
class Trade:
    side: str
    signal_ts: int
    entry_ts: int
    entry: float
    exit_ts: int
    exit: float
    outcome: str
    pnl: float
    r_multiple: float
    cost: float
    bars_held: int


def run_backtest(series: CandleSeries, config: ValidatedConfig, registry: StrategyRegistry, *,
                 allow_synthetic: bool = False, start_index: int | None = None) -> list[Trade]:
    costs = config.profile["costs"]
    half_spread = costs["spread"] / 2
    slip, comm = costs["slippage"], costs["commission"]
    max_hold = config.profile["max_holding_bars"]
    c = series.candles
    trades: list[Trade] = []
    i = start_index if start_index is not None else 1
    while i < len(c) - 1:
        spread_now = c[i].spread if c[i].spread is not None else costs["spread"]
        rec = evaluate(series.window(i, LOOKBACK), config, registry,
                       account=AccountState(open_positions=0, current_spread=spread_now),
                       allow_synthetic=allow_synthetic)
        if rec.decision is Decision.NO_TRADE:
            i += 1
            continue
        stops = [r.stop_distance for r in rec.strategy_results
                 if r.decision is rec.decision and r.stop_distance]
        targets = [r.target_distance for r in rec.strategy_results
                   if r.decision is rec.decision and r.target_distance]
        stop_d, tgt_d = max(stops), (min(targets) if targets else None)
        long = rec.decision is Decision.BUY
        sgn = 1 if long else -1
        e = i + 1
        entry = c[e].open + sgn * (half_spread + slip)
        sl = entry - sgn * stop_d
        tp = entry + sgn * tgt_d if tgt_d else None
        exit_px, exit_i, outcome = None, None, None
        for j in range(e, min(e + max_hold, len(c))):
            b = c[j]
            hit_sl = b.low <= sl if long else b.high >= sl
            hit_tp = tp is not None and (b.high >= tp if long else b.low <= tp)
            if hit_sl:
                exit_px, exit_i, outcome = sl - sgn * slip, j, "STOP" if not hit_tp else "STOP_AMBIGUOUS"
                break
            if hit_tp:
                exit_px, exit_i, outcome = tp, j, "TARGET"
                break
        if exit_px is None:
            exit_i = min(e + max_hold, len(c)) - 1
            exit_px, outcome = c[exit_i].close - sgn * (half_spread + slip), "TIME"
        cost = 2 * (half_spread + slip) + comm
        pnl = sgn * (exit_px - entry) - comm
        trades.append(Trade(rec.decision.value, c[i].ts, c[e].ts, round(entry, 4), c[exit_i].ts,
                            round(exit_px, 4), outcome, round(pnl, 4), round(pnl / stop_d, 4),
                            round(cost, 4), exit_i - e + 1))
        i = exit_i + 1  # one position at a time (max_open_positions respected)
    return trades


def metrics(trades: list[Trade], total_bars: int | None = None) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate_pct": None, "expectancy": None,
                "expectancy_r": None, "profit_factor": None, "net_points": 0.0,
                "max_drawdown_points": 0.0, "total_costs": 0.0, "exposure_pct": 0.0,
                "sample_warning": "NO_TRADES"}
    pnl = [t.pnl for t in trades]
    gw = sum(p for p in pnl if p > 0)
    gl = -sum(p for p in pnl if p < 0)
    eq = peak = dd = 0.0
    for p in pnl:
        eq += p
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    pf = gw / gl if gl > 0 else (math.inf if gw > 0 else None)
    out = {
        "trades": n, "wins": sum(p > 0 for p in pnl), "losses": sum(p < 0 for p in pnl),
        "win_rate_pct": round(100 * sum(p > 0 for p in pnl) / n, 2),
        "expectancy": round(sum(pnl) / n, 4),
        "expectancy_r": round(sum(t.r_multiple for t in trades) / n, 4),
        "profit_factor": None if pf is None else ("inf" if math.isinf(pf) else round(pf, 4)),
        "net_points": round(sum(pnl), 4), "max_drawdown_points": round(dd, 4),
        "total_costs": round(sum(t.cost for t in trades), 4),
        "exposure_pct": round(100 * sum(t.bars_held for t in trades) / total_bars, 2) if total_bars else None,
        "sample_warning": "BELOW_30_TRADES" if n < 30 else None,
    }
    return out


def split_metrics(trades: list[Trade], series: CandleSeries, oos_fraction: float = 0.3) -> dict:
    """Chronological in-sample / out-of-sample split on signal time.

    No parameter is fitted in this milestone; the split reports stability and
    reserves the final segment as holdout for any future optimisation.
    """
    c = series.candles
    cut_index = int(len(c) * (1 - oos_fraction))
    cut_ts = c[cut_index].ts
    ins = [t for t in trades if t.signal_ts < cut_ts]
    oos = [t for t in trades if t.signal_ts >= cut_ts]
    return {"split_ts": cut_ts, "oos_fraction": oos_fraction,
            "in_sample": metrics(ins, cut_index), "out_of_sample": metrics(oos, len(c) - cut_index),
            "all": metrics(trades, len(c))}


def trades_to_rows(trades: list[Trade]) -> list[dict]:
    return [asdict(t) for t in trades]
