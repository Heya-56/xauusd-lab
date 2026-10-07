import os
from datetime import datetime
from typing import Optional

import requests

from .base import MarketDataAdapter


class IBKRAdapter(MarketDataAdapter):
    """IBKR Client Portal Web API market-data adapter.

    This adapter reads real IBKR XAUUSD spot data. It never places orders.
    Required environment variables:
      IBKR_BASE_URL (default: https://localhost:5000/v1/api)
      IBKR_CONID
      IBKR_TOKEN (Bearer token, if the gateway/API requires one)
    """

    name = "ibkr"

    def __init__(self, base_url: Optional[str] = None, conid: Optional[int] = None, token: Optional[str] = None):
        self.base_url = (base_url or os.getenv("IBKR_BASE_URL", "https://localhost:5000/v1/api")).rstrip("/")
        raw_conid = conid or os.getenv("IBKR_CONID")
        if not raw_conid:
            raise ValueError("IBKR_CONID is required for the XAUUSD spot contract")
        self.conid = int(raw_conid)
        self.token = token or os.getenv("IBKR_TOKEN")
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        # Client Portal Gateway commonly uses a local self-signed certificate.
        self.verify_tls = os.getenv("IBKR_VERIFY_TLS", "false").lower() == "true"

    def _get(self, path, params):
        r = self.session.get(f"{self.base_url}{path}", params=params, timeout=30, verify=self.verify_tls)
        r.raise_for_status()
        payload = r.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"IBKR API error: {payload['error']}")
        return payload

    def candles(self, symbol="XAUUSD", timeframe="5m", start=None, end=None):
        if symbol.upper() != "XAUUSD":
            raise ValueError("This adapter is intentionally restricted to spot XAUUSD")
        bar = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "1d": "1d"}.get(timeframe)
        if not bar:
            raise ValueError(f"Unsupported IBKR timeframe: {timeframe}")

        # IBKR's history endpoint uses a period ending at startTime when direction=-1.
        period = os.getenv("IBKR_HISTORY_PERIOD", "30d")
        params = {
            "conid": self.conid,
            "period": period,
            "bar": bar,
            "outsideRth": "true",
            "source": "Midpoint",
            "direction": "-1",
        }
        if start:
            if isinstance(start, datetime):
                start = start.strftime("%Y%m%d-%H:%M:%S")
            params["startTime"] = start
        payload = self._get("/iserver/marketdata/history", params)

        rows = []
        for b in payload.get("data", []):
            rows.append({
                "timestamp": datetime.fromtimestamp(b["t"] / 1000),
                "open": float(b["o"]),
                "high": float(b["h"]),
                "low": float(b["l"]),
                "close": float(b["c"]),
                "volume": float(b.get("v", 0) or 0),
                "source": "IBKR",
                "symbol": "XAUUSD",
            })
        return rows
