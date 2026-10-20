"""Données de recherche Yahoo Finance (GC=F = future or COMEX, PAS le spot XAUUSD).
Sans dépendance : urllib uniquement. À réserver au prototypage ; IBKR/MT5 font foi en paper."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .base import MarketDataAdapter

RANGES = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d", "1d": "10y"}


class YahooAdapter(MarketDataAdapter):
    name = "yahoo"

    def candles(self, symbol="XAUUSD", timeframe="5m", start=None, end=None):
        ticker = "GC=F" if symbol.upper() == "XAUUSD" else symbol
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker, safe='')}"
               f"?range={RANGES.get(timeframe, '60d')}&interval={timeframe}&events=history")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read().decode())["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        out = []
        for i, t in enumerate(res.get("timestamp", [])):
            if None in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]):
                continue
            out.append({"ts": datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
                        "open": float(q["open"][i]), "high": float(q["high"][i]),
                        "low": float(q["low"][i]), "close": float(q["close"][i]),
                        "volume": float(q["volume"][i] or 0)})
        return out
