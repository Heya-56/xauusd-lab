"""Deterministic 0-10 strategy score from backtest metrics (no AI involved).

Tiers:
  score < 5            REJECTED    (red)
  5 <= score < 6       WATCH       (orange) - keep observing, not tradable
  score >= 6           RETAINED    (green)  - eligible for PAPER trading only;
                                              live trading stays a human decision.

Components (weights sum to 10), all computed from recorded metrics:
  3.0  out-of-sample expectancy in R     0 R -> 0 pts, >= 0.30 R -> full
  2.0  out-of-sample profit factor       1.0 -> 0 pts, >= 1.8 -> full
  2.0  IS/OOS stability                  same sign and OOS >= 50% of IS -> full
  2.0  recovery factor (net / max DD)    0 -> 0 pts, >= 2.0 -> full
  1.0  sample size (all trades)          30 -> 0.5 pts, >= 100 -> full
Hard gates (applied after the weighted sum):
  fewer than 30 trades in total          -> capped at 4.0  (INSUFFICIENT_SAMPLE)
  fewer than 10 out-of-sample trades     -> capped at 4.5  (INSUFFICIENT_OOS)
  out-of-sample expectancy <= 0          -> capped at 4.9  (OOS_NOT_PROFITABLE)
  synthetic (non-market) data            -> capped at 0.0  (SYNTHETIC_DATA)
The weights and thresholds are versioned (SCORE_VERSION); changing them is a
reviewed code change, never something an agent or the dashboard can alter.
"""
from __future__ import annotations

SCORE_VERSION = "score_v1"
WATCH_THRESHOLD = 5.0
RETAIN_THRESHOLD = 6.0


def _lin(x: float | None, lo: float, hi: float) -> float:
    if x is None:
        return 0.0
    if x <= lo:
        return 0.0
    if x >= hi:
        return 1.0
    return (x - lo) / (hi - lo)


def _pf(v) -> float | None:
    if v is None:
        return None
    if v == "inf":
        return 99.0
    return float(v)


def score_strategy(split: dict, *, synthetic: bool = False) -> dict:
    """`split` is the output of core.backtest.split_metrics()."""
    a, i, o = split["all"], split["in_sample"], split["out_of_sample"]
    comp = {}
    comp["oos_expectancy_r"] = 3.0 * _lin(o.get("expectancy_r"), 0.0, 0.30)
    comp["oos_profit_factor"] = 2.0 * _lin(_pf(o.get("profit_factor")), 1.0, 1.8)
    ie, oe = i.get("expectancy_r"), o.get("expectancy_r")
    if ie is None or oe is None or ie <= 0 or oe <= 0:
        stab = 0.0
    else:
        stab = min(1.0, oe / (0.5 * ie)) if ie > 0 else 0.0
    comp["stability"] = 2.0 * stab
    dd = a.get("max_drawdown_points") or 0.0
    rf = (a.get("net_points") or 0.0) / dd if dd > 0 else (1e9 if (a.get("net_points") or 0) > 0 else 0.0)
    comp["recovery_factor"] = 2.0 * _lin(rf, 0.0, 2.0)
    n = a.get("trades") or 0
    comp["sample_size"] = 0.0 if n < 30 else 0.5 + 0.5 * _lin(n, 30, 100)
    raw = round(sum(comp.values()), 2)

    score, gates = raw, []
    if synthetic:
        score, gates = 0.0, ["SYNTHETIC_DATA"]
    else:
        if n < 30:
            score, gates = min(score, 4.0), gates + ["INSUFFICIENT_SAMPLE"]
        if (o.get("trades") or 0) < 10:
            score, gates = min(score, 4.5), gates + ["INSUFFICIENT_OOS"]
        if oe is None or oe <= 0:
            score, gates = min(score, 4.9), gates + ["OOS_NOT_PROFITABLE"]
    score = round(score, 2)
    tier = "RETAINED" if score >= RETAIN_THRESHOLD else ("WATCH" if score >= WATCH_THRESHOLD else "REJECTED")
    return {"score": score, "raw_score": raw, "tier": tier, "gates": gates,
            "components": {k: round(v, 3) for k, v in comp.items()},
            "score_version": SCORE_VERSION,
            "eligible_for": "paper_trading" if tier == "RETAINED" else None}
