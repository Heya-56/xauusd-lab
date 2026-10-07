import csv
import io
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

TAHITI = timezone(timedelta(hours=-10))

def ema(values, span):
    a = 2.0 / (span + 1.0)
    out = []
    prev = None
    for v in values:
        prev = v if prev is None else a * v + (1-a) * prev
        out.append(prev)
    return out

def fetch_yahoo():
    symbol = urllib.parse.quote("GC=F", safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=60d&interval=5m&events=history"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode())
    result = payload["chart"]["result"][0]
    q = result["indicators"]["quote"][0]
    rows = []
    for i, ts in enumerate(result["timestamp"]):
        if q["open"][i] is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        rows.append({
            "utc": dt.isoformat(),
            "local": dt.astimezone(TAHITI),
            "open": float(q["open"][i]),
            "high": float(q["high"][i]),
            "low": float(q["low"][i]),
            "close": float(q["close"][i]),
        })
    return rows

def macd(rows):
    closes = [r["close"] for r in rows]
    fast, slow = ema(closes, 12), ema(closes, 26)
    line = [a-b for a,b in zip(fast, slow)]
    signal = ema(line, 9)
    hist = [a-b for a,b in zip(line, signal)]
    return line, signal, hist

def backtest(rows):
    line, signal, hist = macd(rows)
    trades = []
    used_days = set()
    for i in range(26, len(rows)-1):
        r = rows[i]
        d = r["local"]
        if d.weekday() not in (0,2,4) or d.hour != 14 or d.minute != 0:
            continue
        day = d.date().isoformat()
        if day in used_days:
            continue
        # Faithful core of 3aLaee/xauusd-trading-bot: MACD cross + 10-bar support/resistance.
        cross_up = line[i] > signal[i] and line[i-1] <= signal[i-1]
        cross_dn = line[i] < signal[i] and line[i-1] >= signal[i-1]
        resistance = max(x["high"] for x in rows[max(0,i-9):i+1])
        support = min(x["low"] for x in rows[max(0,i-9):i+1])
        direction = None
        if cross_dn and hist[i] < 0 and r["close"] < resistance:
            direction = "SHORT"
        elif cross_up and hist[i] > 0 and r["close"] > support:
            direction = "LONG"
        if not direction:
            continue
        entry = r["close"]
        sl_dist, tp_dist = 0.15, 0.10
        sl = entry + sl_dist if direction=="SHORT" else entry-sl_dist
        tp = entry - tp_dist if direction=="SHORT" else entry+tp_dist
        outcome = "OPEN"
        exit_price = rows[-1]["close"]
        exit_time = rows[-1]["utc"]
        for j in range(i+1, min(i+25, len(rows))):
            b = rows[j]
            hit_sl = b["high"] >= sl if direction=="SHORT" else b["low"] <= sl
            hit_tp = b["low"] <= tp if direction=="SHORT" else b["high"] >= tp
            if hit_sl and hit_tp:
                outcome, exit_price, exit_time = "SL_AMBIGUOUS", sl, b["utc"]
                break
            if hit_sl:
                outcome, exit_price, exit_time = "SL", sl, b["utc"]
                break
            if hit_tp:
                outcome, exit_price, exit_time = "TP", tp, b["utc"]
                break
        pnl = (exit_price-entry) if direction=="LONG" else (entry-exit_price)
        trades.append({
            "date": day, "direction": direction, "entry": round(entry,2),
            "exit": round(exit_price,2), "pnl": round(pnl,2),
            "outcome": outcome, "entry_utc": r["utc"], "exit_utc": exit_time
        })
        used_days.add(day)
    return trades

def main():
    rows = fetch_yahoo()
    trades = backtest(rows)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    losses = sum(1 for t in trades if t["pnl"] < 0)
    net = sum(t["pnl"] for t in trades)
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    pf = gross_win/gross_loss if gross_loss else math.inf
    result = {
        "lab": "XAUUSD Lab",
        "data": "Yahoo Finance GC=F (COMEX gold futures proxy, NOT spot XAUUSD)",
        "timeframe": "5m",
        "window": "60d",
        "schedule": "14:00 Pacific/Tahiti, Mon/Wed/Fri",
        "candidate": "3aLaee/xauusd-trading-bot core MACD/support-resistance logic",
        "trades": len(trades), "wins": wins, "losses": losses,
        "win_rate_pct": round(100*wins/len(trades),2) if trades else 0,
        "net_price_points": round(net,2),
        "profit_factor": round(pf,3) if math.isfinite(pf) else None,
    }
    print(json.dumps(result, indent=2))
    with open("lab_result.json","w") as f: json.dump({"summary":result,"trades":trades}, f, indent=2)
    with open("lab_trades.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=trades[0].keys() if trades else ["date"])
        w.writeheader(); w.writerows(trades)

if __name__ == "__main__":
    main()
