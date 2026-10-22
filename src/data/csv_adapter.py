"""Lecture de bougies depuis un CSV (export MT5, TradingView, Dukascopy…).

Colonnes reconnues (insensible à la casse) : time/date/datetime/timestamp, open, high, low, close, volume/tick_volume.
Le format MT5 « <DATE> <TIME> » séparé par tabulations est aussi accepté.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from .base import MarketDataAdapter

TIME_KEYS = ("timestamp", "datetime", "time", "date", "ts")


def _norm(k: str) -> str:
    return k.strip().strip("<>").lower()


def _parse_time(row: dict) -> str:
    if "date" in row and "time" in row and row["time"] and ":" in row["time"]:
        raw = f"{row['date']} {row['time']}"
    else:
        raw = next(row[k] for k in TIME_KEYS if row.get(k))
    raw = raw.strip()
    if raw.isdigit():
        n = int(raw)
        dt = datetime.fromtimestamp(n / 1000 if n > 10**11 else n, tz=timezone.utc)
    else:
        raw = raw.replace(".", "-", 2) if raw[:4].isdigit() and raw[4:5] == "." else raw
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class CsvAdapter(MarketDataAdapter):
    name = "csv"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def candles(self, symbol="XAUUSD", timeframe=None, start=None, end=None):
        text = self.path.read_text(encoding="utf-8-sig")
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
        rows = []
        for raw in csv.DictReader(text.splitlines(), dialect=dialect):
            r = {_norm(k): v for k, v in raw.items() if k}
            vol = r.get("volume") or r.get("tick_volume") or r.get("tickvol") or r.get("vol") or 0
            rows.append({"ts": _parse_time(r), "open": float(r["open"]), "high": float(r["high"]),
                         "low": float(r["low"]), "close": float(r["close"]), "volume": float(vol or 0)})
        rows.sort(key=lambda x: x["ts"])
        if start:
            rows = [x for x in rows if x["ts"] >= str(start)]
        if end:
            rows = [x for x in rows if x["ts"] <= str(end)]
        return rows
