import csv
import json
import math
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
PARIS = ZoneInfo("Europe/Paris")
SYMBOL = "GC=F"
TIMEFRAME = "1h"

def yahoo(symbol=SYMBOL, range_="2y", interval=TIMEFRAME):
    u = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol, safe='')}?range={range_}&interval={interval}&events=history"
    )
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.loads(r.read().decode())

    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(result["timestamp"]):
        if quote["close"][i] is None:
            continue
        utc_dt = datetime.fromtimestamp(ts, tz=UTC)
        out.append({
            "utc": utc_dt,
            "local": utc_dt.astimezone(PARIS),
            "open": float(quote["open"][i]),
            "high": float(quote["high"][i]),
            "low": float(quote["low"][i]),
            "close": float(quote["close"][i]),
        })
    return out

def ema(values, n):
    k = 2 / (n + 1)
    out = []
    prev = None
    for x in values:
        prev = x if prev is None else k * x + (1 - k) * prev
        out.append(prev)
    return out

def rsi(values, n=14):
    out = [None] * len(values)
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
        if i >= n:
            g = sum(gains[-n:]) / n
            l = sum(losses[-n:]) / n
            out[i] = 100 if l == 0 else 100 - 100 / (1 + g / l)
    return out

def atr(rows, n=14):
    tr = []
    for i, row in enumerate(rows):
        if i == 0:
            tr.append(row["high"] - row["low"])
        else:
            tr.append(max(
                row["high"] - row["low"],
                abs(row["high"] - rows[i - 1]["close"]),
                abs(row["low"] - rows[i - 1]["close"]),
            ))
    out = [None] * len(rows)
    for i in range(n - 1, len(rows)):
        out[i] = sum(tr[i - n + 1:i + 1]) / n
    return out

def max_drawdown(pnls):
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return abs(max_dd)

def run(rows, name, signal_fn, hour, horizon_hours, sl_mult=1.2, tp_mult=1.8):
    trades = []
    last_day = None

    for i in range(80, len(rows) - horizon_hours - 1):
        row = rows[i]
        local = row["local"]

        # Protocol is expressed in France time, not Tahiti time.
        if local.weekday() not in (0, 2, 4) or local.hour != hour:
            continue
        if last_day == local.date():
            continue

        signal = signal_fn(i)
        if not signal:
            continue

        entry = row["close"]
        a = ATR[i] or 0
        if a <= 0:
            continue

        sl = entry - sl_mult * a if signal == "LONG" else entry + sl_mult * a
        tp = entry + tp_mult * a if signal == "LONG" else entry - tp_mult * a

        exit_price = rows[i + horizon_hours]["close"]
        outcome = "TIME"

        for j in range(i + 1, i + horizon_hours + 1):
            bar = rows[j]
            hit_sl = bar["low"] <= sl if signal == "LONG" else bar["high"] >= sl
            hit_tp = bar["high"] >= tp if signal == "LONG" else bar["low"] <= tp

            # Conservative ambiguity rule: if both are touched in one bar,
            # assume the stop was hit first.
            if hit_sl:
                outcome, exit_price = "SL", sl
                break
            if hit_tp:
                outcome, exit_price = "TP", tp
                break

        pnl = exit_price - entry if signal == "LONG" else entry - exit_price
        trades.append({
            "date": str(local.date()),
            "timestamp_paris": local.isoformat(),
            "direction": signal,
            "entry": round(entry, 4),
            "exit": round(exit_price, 4),
            "pnl": round(pnl, 4),
            "outcome": outcome,
            "hour_paris": hour,
            "horizon_hours": horizon_hours,
        })
        last_day = local.date()

    pnls = [t["pnl"] for t in trades]
    wins = sum(p > 0 for p in pnls)
    losses = sum(p < 0 for p in pnls)
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    avg = sum(pnls) / len(pnls) if pnls else 0.0
    stdev = math.sqrt(sum((p - avg) ** 2 for p in pnls) / (len(pnls) - 1)) if len(pnls) > 1 else 0.0
    sharpe_like = avg / stdev * math.sqrt(len(pnls)) if stdev else None

    return {
        "candidate": name,
        "timezone": "Europe/Paris",
        "hour_paris": hour,
        "horizon_hours": horizon_hours,
        "sl_atr": sl_mult,
        "tp_atr": tp_mult,
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(100 * wins / len(trades), 2) if trades else 0,
        "net": round(sum(pnls), 4),
        "avg_pnl": round(avg, 4),
        "max_drawdown": round(max_drawdown(pnls), 4),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else None,
        "sharpe_like": round(sharpe_like, 4) if sharpe_like is not None else None,
        "trades_detail": trades,
    }

def make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        created_at_utc TEXT NOT NULL,
        source TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        data_timezone TEXT NOT NULL,
        data_start TEXT,
        data_end TEXT,
        protocol_version TEXT NOT NULL,
        note TEXT
    );

    CREATE TABLE IF NOT EXISTS experiments (
        experiment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        test_number INTEGER NOT NULL,
        candidate TEXT NOT NULL,
        hour_paris INTEGER NOT NULL,
        horizon_hours INTEGER NOT NULL,
        sl_atr REAL NOT NULL,
        tp_atr REAL NOT NULL,
        trades INTEGER NOT NULL,
        wins INTEGER NOT NULL,
        losses INTEGER NOT NULL,
        win_rate_pct REAL NOT NULL,
        net REAL NOT NULL,
        avg_pnl REAL NOT NULL,
        max_drawdown REAL NOT NULL,
        profit_factor REAL,
        sharpe_like REAL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
    );

    CREATE TABLE IF NOT EXISTS trades (
        trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id INTEGER NOT NULL,
        trade_date TEXT NOT NULL,
        timestamp_paris TEXT NOT NULL,
        direction TEXT NOT NULL,
        entry REAL NOT NULL,
        exit REAL NOT NULL,
        pnl REAL NOT NULL,
        outcome TEXT NOT NULL,
        FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
    );

    CREATE INDEX IF NOT EXISTS idx_experiments_candidate ON experiments(candidate);
    CREATE INDEX IF NOT EXISTS idx_experiments_net ON experiments(net);
    CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);
    """)
    return conn

rows = yahoo()
closes = [r["close"] for r in rows]
E20 = ema(closes, 20)
E50 = ema(closes, 50)
E200 = ema(closes, 200)
R = rsi(closes)
ATR = atr(rows)

def macd(i):
    fast = ema(closes, 12)
    slow = ema(closes, 26)
    m = [a - b for a, b in zip(fast, slow)]
    s = ema(m, 9)
    if m[i] > s[i] and m[i - 1] <= s[i - 1]:
        return "LONG"
    if m[i] < s[i] and m[i - 1] >= s[i - 1]:
        return "SHORT"

def trend_pullback(i):
    if E50[i] > E200[i] and closes[i] <= E20[i] * 1.002 and R[i] is not None and R[i] < 55:
        return "LONG"
    if E50[i] < E200[i] and closes[i] >= E20[i] * 0.998 and R[i] is not None and R[i] > 45:
        return "SHORT"

def donchian(i):
    hi = max(x["high"] for x in rows[i - 24:i])
    lo = min(x["low"] for x in rows[i - 24:i])
    if closes[i] > hi and E50[i] > E200[i]:
        return "LONG"
    if closes[i] < lo and E50[i] < E200[i]:
        return "SHORT"

def meanrev(i):
    if R[i] is None:
        return None
    if R[i] < 30 and closes[i] < E20[i]:
        return "LONG"
    if R[i] > 70 and closes[i] > E20[i]:
        return "SHORT"

def breakout(i):
    hi = max(x["high"] for x in rows[i - 12:i])
    lo = min(x["low"] for x in rows[i - 12:i])
    if closes[i] > hi and E20[i] > E50[i]:
        return "LONG"
    if closes[i] < lo and E20[i] < E50[i]:
        return "SHORT"

candidates = [
    ("MACD cross (3aLaee core)", macd),
    ("EMA20/50/200 trend pullback (omidram-style)", trend_pullback),
    ("Donchian breakout + EMA trend", donchian),
    ("RSI mean reversion", meanrev),
    ("12-bar breakout + EMA filter", breakout),
]

# 5 candidate families x 10 controlled protocol variants = 50 tests.
# Times are France time and deliberately cover London + New York activity.
hours = [8, 10, 12, 14, 16]
horizons = [6, 12]

run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
db_path = "xauusd_lab.sqlite"
conn = make_db(db_path)
conn.execute(
    "INSERT INTO runs(run_id,created_at_utc,source,symbol,timeframe,data_timezone,"
    "data_start,data_end,protocol_version,note) VALUES(?,?,?,?,?,?,?,?,?,?)",
    (
        run_id,
        datetime.now(UTC).isoformat(),
        "Yahoo Finance GC=F",
        "XAUUSD-proxy-GC=F",
        TIMEFRAME,
        "Europe/Paris",
        rows[0]["local"].isoformat() if rows else None,
        rows[-1]["local"].isoformat() if rows else None,
        "v0.2-50-tests",
        "Research only. GC=F is COMEX gold futures, not spot XAUUSD.",
    ),
)

all_results = []
test_number = 0

for candidate_name, signal_fn in candidates:
    for hour in hours:
        for horizon in horizons:
            test_number += 1
            result = run(rows, candidate_name, signal_fn, hour, horizon)
            all_results.append(result)

            cur = conn.execute(
                "INSERT INTO experiments(run_id,test_number,candidate,hour_paris,horizon_hours,"
                "sl_atr,tp_atr,trades,wins,losses,win_rate_pct,net,avg_pnl,max_drawdown,"
                "profit_factor,sharpe_like) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id, test_number, candidate_name, hour, horizon,
                    result["sl_atr"], result["tp_atr"], result["trades"],
                    result["wins"], result["losses"], result["win_rate_pct"],
                    result["net"], result["avg_pnl"], result["max_drawdown"],
                    result["profit_factor"], result["sharpe_like"],
                ),
            )
            experiment_id = cur.lastrowid

            conn.executemany(
                "INSERT INTO trades(experiment_id,trade_date,timestamp_paris,direction,"
                "entry,exit,pnl,outcome) VALUES(?,?,?,?,?,?,?,?)",
                [
                    (
                        experiment_id, t["date"], t["timestamp_paris"], t["direction"],
                        t["entry"], t["exit"], t["pnl"], t["outcome"]
                    )
                    for t in result["trades_detail"]
                ],
            )

conn.commit()
conn.close()

summary = []
for r in all_results:
    summary.append({k: v for k, v in r.items() if k != "trades_detail"})

# Rank by robustness, not simply by the highest raw profit.
# Minimum 30 trades prevents tiny samples from winning the leaderboard.
def rank_key(x):
    enough = x["trades"] >= 30
    pf = x["profit_factor"] if x["profit_factor"] is not None else -999
    return (1 if enough else 0, pf, x["net"], x["sharpe_like"] or -999, -x["max_drawdown"])

ranking = sorted(summary, key=rank_key, reverse=True)

payload = {
    "lab": "XAUUSD Lab",
    "run_id": run_id,
    "source": "Yahoo Finance GC=F (COMEX gold futures proxy, NOT spot XAUUSD)",
    "timeframe": TIMEFRAME,
    "timezone": "Europe/Paris",
    "protocol": "5 candidate families x 5 France-time entries x 2 horizons = 50 tests; Mon/Wed/Fri; max 1 trade/day/test; ATR 1.2 SL / 1.8 TP",
    "data_start": rows[0]["local"].isoformat() if rows else None,
    "data_end": rows[-1]["local"].isoformat() if rows else None,
    "tests": 50,
    "ranking": ranking,
}

with open("competition.json", "w", encoding="utf-8") as f:
    json.dump({"summary": ranking, "results": all_results, "meta": payload}, f, indent=2)

with open("competition.csv", "w", newline="", encoding="utf-8") as f:
    fields = list(ranking[0].keys())
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(ranking)

print(json.dumps(payload, indent=2))
