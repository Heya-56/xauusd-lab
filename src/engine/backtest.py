"""Backtest bougie par bougie, avec coûts, moteur de risque et découpage in-sample / out-of-sample."""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from src.engine.position import Position
from src.engine.risk import RiskManager

LOOKBACK = 600  # fenêtre glissante : temps de calcul linéaire au lieu de quadratique

DAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


def _parse_ts(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


class SessionFilter:
    def __init__(self, cfg: dict):
        exp = cfg.get("experiment", {})
        self.tz = ZoneInfo(exp.get("timezone", "UTC"))
        self.days = {DAYS[d] for d in exp.get("days", DAYS)}
        win = exp.get("entry_window")
        self.window = tuple(win) if win else None

    def allows(self, ts) -> bool:
        local = _parse_ts(ts).astimezone(self.tz)
        if local.weekday() not in self.days:
            return False
        if self.window:
            hm = local.strftime("%H:%M")
            return self.window[0] <= hm < self.window[1]
        return True

    def day(self, ts) -> str:
        return _parse_ts(ts).astimezone(self.tz).date().isoformat()


def metrics(trades: list[dict], start_equity: float) -> dict:
    pnls = [t["pnl"] for t in trades]
    rs = [t["r"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    eq, peak, mdd = start_equity, start_equity, 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak * 100 if peak else 0)
    gl = -sum(losses)
    n = len(trades)
    return {
        "trades": n,
        "win_rate_pct": round(100 * len(wins) / n, 2) if n else 0.0,
        "net_pnl": round(sum(pnls), 2),
        "net_r": round(sum(rs), 2),
        "expectancy_r": round(sum(rs) / n, 3) if n else 0.0,
        "profit_factor": round(sum(wins) / gl, 3) if gl else (None if not wins else math.inf),
        "max_drawdown_pct": round(mdd, 2),
        "end_equity": round(start_equity + sum(pnls), 2),
        "enough_trades": n >= 30,
    }


def run_backtest(candles: list[dict], strategy, cfg: dict, equity: float = 10_000.0) -> dict:
    costs = cfg.get("costs", {})
    cost_side = float(costs.get("spread", 0.0)) / 2 + float(costs.get("slippage", 0.0))
    rm = RiskManager(cfg)
    sess = SessionFilter(cfg)
    max_bars = int(cfg.get("experiment", {}).get("max_bars_in_trade", 0)) or None

    start_equity = equity
    trades, rejected = [], {}
    pos: Position | None = None
    bars_in_trade = 0
    cur_day, day_start_eq, realized_today, trades_today = None, equity, 0.0, 0

    for i, bar in enumerate(candles):
        day = sess.day(bar["ts"])
        if day != cur_day:
            cur_day, day_start_eq, realized_today, trades_today = day, equity, 0.0, 0

        if pos and pos.is_open:
            bars_in_trade += 1
            before = pos.realized
            pos.update(bar)
            if pos.is_open and max_bars and bars_in_trade >= max_bars:
                pos.force_close(bar["close"], bar["ts"], "TIME")
            delta = pos.realized - before
            equity += delta
            realized_today += delta
            if not pos.is_open:
                trades.append(_trade_row(pos))
                pos = None

        if pos is not None or i + 1 < strategy.warmup or not sess.allows(bar["ts"]):
            continue
        sig = strategy.evaluate(candles[max(0, i + 1 - LOOKBACK): i + 1])
        if sig.action == "NONE":
            continue
        d = rm.evaluate(equity=equity, day_start_equity=day_start_eq, realized_today=realized_today,
                        open_positions=0, trades_today=trades_today, entry=sig.entry, stop=sig.stop_loss)
        if not d.allowed:
            rejected[d.reason] = rejected.get(d.reason, 0) + 1
            continue
        pos = Position(sig.action, sig.entry, sig.stop_loss, sig.tp1, sig.tp2, d.size_lots, bar["ts"],
                       rm.contract_size, cost_side)
        bars_in_trade, trades_today = 0, trades_today + 1

    if pos and pos.is_open:
        before = pos.realized
        pos.force_close(candles[-1]["close"], candles[-1]["ts"], "END")
        equity += pos.realized - before
        trades.append(_trade_row(pos))

    split = float(cfg.get("validation", {}).get("in_sample_ratio", 0.7))
    cut_ts = candles[int(len(candles) * split)]["ts"] if candles else None
    ins = [t for t in trades if t["opened_at"] < cut_ts] if cut_ts else trades
    oos = [t for t in trades if t["opened_at"] >= cut_ts] if cut_ts else []
    eq_oos = start_equity + sum(t["pnl"] for t in ins)
    return {
        "strategy": strategy.name,
        "bars": len(candles),
        "period": [str(candles[0]["ts"]), str(candles[-1]["ts"])] if candles else None,
        "costs_per_side": cost_side,
        "all": metrics(trades, start_equity),
        "in_sample": metrics(ins, start_equity),
        "out_of_sample": metrics(oos, eq_oos),
        "rejected_by_risk": rejected,
        "trades": trades,
    }


def _trade_row(p: Position) -> dict:
    return {"opened_at": str(p.opened_at), "closed_at": str(p.closed_at), "side": p.side,
            "entry": round(p.entry, 4), "stop": round(p.initial_stop, 4), "lots": p.lots,
            "outcome": p.outcome, "pnl": round(p.realized, 2), "r": round(p.r_multiple, 3)}
