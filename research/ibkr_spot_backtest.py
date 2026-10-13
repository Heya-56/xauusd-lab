"""Run a research-only XAUUSD backtest against IBKR historical midpoint bars.

Run on the same machine as IB Gateway/TWS Paper:
  python research/ibkr_spot_backtest.py

This script never submits orders. It requires an authenticated Paper Gateway session.
Historical midpoint bars do not contain historical bid/ask spread; costs are reported
as unmodelled unless XAUUSD_ROUND_TRIP_COST is set to a conservative price-unit estimate.
"""
from __future__ import annotations

import csv
import json
import math
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.data.ibkr_gateway import IBKRGatewayAdapter

PARIS = ZoneInfo("Europe/Paris")
OUT = Path("reports")
HOURS = (8, 10, 12, 14, 16)
HORIZONS = (6, 12)
ROUND_TRIP_COST = float(os.getenv("XAUUSD_ROUND_TRIP_COST", "0"))


def ema(values, period):
    k = 2 / (period + 1)
    out = []
    prev = None
    for value in values:
        prev = value if prev is None else k * value + (1 - k) * prev
        out.append(prev)
    return out


def rsi(values, period=14):
    out = [None] * len(values)
    for i in range(period, len(values)):
        changes = [values[j] - values[j - 1] for j in range(i - period + 1, i + 1)]
        gains = sum(max(x, 0) for x in changes) / period
        losses = sum(max(-x, 0) for x in changes) / period
        out[i] = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
    return out


def atr(rows, period=14):
    tr = []
    for i, row in enumerate(rows):
        if i == 0:
            tr.append(row["high"] - row["low"])
        else:
            prev = rows[i - 1]["close"]
            tr.append(max(row["high"] - row["low"], abs(row["high"] - prev), abs(row["low"] - prev)))
    out = [None] * len(rows)
    for i in range(period - 1, len(rows)):
        out[i] = sum(tr[i - period + 1:i + 1]) / period
    return out


def max_drawdown(pnls):
    equity = peak = worst = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def run(rows, name, signal, hour, horizon, atrs):
    closes = [r["close"] for r in rows]
    trades = []
    last_day = None
    for i in range(200, len(rows) - horizon - 1):
        dt = datetime.fromisoformat(rows[i]["timestamp"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(PARIS)
        if local.weekday() not in (0, 2, 4) or local.hour != hour or last_day == local.date():
            continue
        side = signal(i, rows, closes)
        a = atrs[i]
        if not side or not a or a <= 0:
            continue
        entry = closes[i]
        sl = entry - 1.2 * a if side == "LONG" else entry + 1.2 * a
        tp = entry + 1.8 * a if side == "LONG" else entry - 1.8 * a
        exit_price = closes[i + horizon]
        outcome = "TIME"
        for j in range(i + 1, i + horizon + 1):
            bar = rows[j]
            hit_sl = bar["low"] <= sl if side == "LONG" else bar["high"] >= sl
            hit_tp = bar["high"] >= tp if side == "LONG" else bar["low"] <= tp
            if hit_sl:  # conservative if SL and TP are both touched in the same bar
                exit_price, outcome = sl, "SL"
                break
            if hit_tp:
                exit_price, outcome = tp, "TP"
                break
        gross = exit_price - entry if side == "LONG" else entry - exit_price
        net = gross - ROUND_TRIP_COST
        trades.append({"timestamp_paris": local.isoformat(), "side": side, "entry": entry,
                       "exit": exit_price, "gross_pnl_price_units": gross,
                       "net_pnl_price_units": net, "outcome": outcome})
        last_day = local.date()
    pnls = [t["net_pnl_price_units"] for t in trades]
    wins = sum(x > 0 for x in pnls)
    gross_win = sum(x for x in pnls if x > 0)
    gross_loss = -sum(x for x in pnls if x < 0)
    return {
        "candidate": name, "entry_hour_paris": hour, "horizon_hours": horizon,
        "trades": len(trades), "wins": wins, "losses": sum(x < 0 for x in pnls),
        "win_rate_pct": round(100 * wins / len(trades), 2) if trades else 0,
        "net_pnl_price_units": round(sum(pnls), 4),
        "max_drawdown_price_units": round(max_drawdown(pnls), 4),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else None,
        "round_trip_cost_price_units": ROUND_TRIP_COST,
        "trades_detail": trades,
    }


def main():
    adapter = IBKRGatewayAdapter()
    try:
        connection = adapter.connect()
        quote = adapter.quote()
        if not connection.get("connected"):
            raise RuntimeError("IBKR Gateway is not connected")
        bars = adapter.candles("XAUUSD", "1h", duration="2 Y")
    finally:
        adapter.close()

    if len(bars) < 300:
        raise RuntimeError(f"Insufficient IBKR history: received {len(bars)} hourly bars; need at least 300")
    closes = [x["close"] for x in bars]
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    r = rsi(closes)
    a = atr(bars)

    macd_fast, macd_slow = ema(closes, 12), ema(closes, 26)
    macd_line = [x - y for x, y in zip(macd_fast, macd_slow)]
    macd_signal = ema(macd_line, 9)

    def macd(i, rows, cs):
        if macd_line[i] > macd_signal[i] and macd_line[i - 1] <= macd_signal[i - 1]: return "LONG"
        if macd_line[i] < macd_signal[i] and macd_line[i - 1] >= macd_signal[i - 1]: return "SHORT"

    def trend(i, rows, cs):
        if e50[i] > e200[i] and cs[i] <= e20[i] * 1.002 and r[i] is not None and r[i] < 55: return "LONG"
        if e50[i] < e200[i] and cs[i] >= e20[i] * 0.998 and r[i] is not None and r[i] > 45: return "SHORT"

    def donchian(i, rows, cs):
        hi = max(x["high"] for x in rows[i - 24:i])
        lo = min(x["low"] for x in rows[i - 24:i])
        if cs[i] > hi and e50[i] > e200[i]: return "LONG"
        if cs[i] < lo and e50[i] < e200[i]: return "SHORT"

    def meanrev(i, rows, cs):
        if r[i] is None: return None
        if r[i] < 30 and cs[i] < e20[i]: return "LONG"
        if r[i] > 70 and cs[i] > e20[i]: return "SHORT"

    def breakout(i, rows, cs):
        hi = max(x["high"] for x in rows[i - 12:i])
        lo = min(x["low"] for x in rows[i - 12:i])
        if cs[i] > hi and e20[i] > e50[i]: return "LONG"
        if cs[i] < lo and e20[i] < e50[i]: return "SHORT"

    candidates = [
        ("MACD cross", macd), ("EMA trend pullback", trend),
        ("Donchian breakout + EMA trend", donchian),
        ("RSI mean reversion", meanrev), ("12-bar breakout + EMA filter", breakout),
    ]
    results = []
    for name, fn in candidates:
        for hour in HOURS:
            for horizon in HORIZONS:
                result = run(bars, name, fn, hour, horizon, a)
                result.pop("trades_detail")
                results.append(result)

    results.sort(key=lambda x: (x["trades"] >= 30, x["profit_factor"] or -1,
                               x["net_pnl_price_units"]), reverse=True)
    OUT.mkdir(exist_ok=True)
    report = {
        "lab": "XAUUSD Lab", "source": "IBKR historical XAUUSD midpoint",
        "contract": connection["contract"], "quote_at_run": quote,
        "bars": len(bars), "first_bar": bars[0]["timestamp"], "last_bar": bars[-1]["timestamp"],
        "tests": len(results), "schedule_timezone": "Europe/Paris",
        "schedule": "Monday/Wednesday/Friday; 5 entry hours x 2 horizons x 5 candidates",
        "stop_atr": 1.2, "take_profit_atr": 1.8,
        "cost_note": ("Configured round-trip cost applied in price units."
                      if ROUND_TRIP_COST else
                      "WARNING: spread/commission/slippage not modelled; do not treat as validated."),
        "results": results,
    }
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = OUT / f"ibkr-xauusd-backtest-{stamp}.json"
    csv_path = OUT / f"ibkr-xauusd-backtest-{stamp}.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[k for k in results[0] if k != "trades_detail"])
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps({"status": "BACKTEST_COMPLETE_RESEARCH_ONLY", "json": str(json_path),
                      "csv": str(csv_path), "bars": len(bars), "tests": len(results),
                      "top_5": results[:5], "cost_note": report["cost_note"]}, indent=2))


if __name__ == "__main__":
    main()
