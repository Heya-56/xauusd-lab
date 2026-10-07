"""IBKR Gateway adapter using ib_async.

Primary XAUUSD data path for the Lab. IB Gateway must be reachable from
the machine running this adapter. Live submission remains disabled here.
"""
from __future__ import annotations
import asyncio
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from .base import MarketDataAdapter

BAR_MAP = {
    "1m": ("1 min", "2 D"), "5m": ("5 mins", "4 D"), "15m": ("15 mins", "6 D"),
    "30m": ("30 mins", "8 D"), "1h": ("1 hour", "25 D"), "4h": ("4 hours", "4 M"),
    "1d": ("1 day", "2 Y"),
}

@dataclass(frozen=True)
class IBKRConfig:
    host: str = os.getenv("IBKR_HOST", "127.0.0.1")
    port: int = int(os.getenv("IBKR_PORT", "4004"))
    client_id: int = int(os.getenv("IBKR_CLIENT_ID", "27"))
    market_data_type: int = int(os.getenv("IBKR_MARKET_DATA_TYPE", "1"))

class IBKRGatewayAdapter(MarketDataAdapter):
    name = "ibkr-gateway"

    def __init__(self, config: IBKRConfig | None = None):
        self.cfg = config or IBKRConfig()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="lab-ibkr-loop")
        self._thread.start()
        self._ib = self._run(self._make_ib(), 10)

    async def _make_ib(self):
        from ib_async import IB
        return IB()

    def _run(self, coro, timeout: float = 30):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    async def _ensure(self):
        if not self._ib.isConnected():
            await self._ib.connectAsync(self.cfg.host, self.cfg.port, clientId=self.cfg.client_id, timeout=20)
            self._ib.reqMarketDataType(self.cfg.market_data_type)

    async def _contract(self):
        from ib_async import Contract
        await self._ensure()
        c = Contract(secType="CMDTY", symbol="XAUUSD", exchange="SMART", currency="USD")
        details = await self._ib.reqContractDetailsAsync(c)
        if not details:
            raise RuntimeError("IBKR: contrat XAUUSD introuvable ou permission spot gold absente")
        return details[0].contract

    def connect(self) -> dict[str, Any]:
        c = self._run(self._contract())
        return {"connected": self._ib.isConnected(), "host": self.cfg.host, "port": self.cfg.port,
                "client_id": self.cfg.client_id,
                "contract": {"conId": getattr(c, "conId", None), "secType": c.secType,
                             "symbol": c.symbol, "exchange": c.exchange, "currency": c.currency}}

    def candles(self, symbol="XAUUSD", timeframe="5m", start=None, end=None):
        if symbol.upper().replace("/", "") != "XAUUSD":
            raise ValueError("Adapter limité à XAUUSD")
        if timeframe not in BAR_MAP:
            raise ValueError(f"Timeframe IBKR non supporté: {timeframe}")

        async def _history():
            c = await self._contract()
            end_dt = ""
            if end:
                end_dt = end.astimezone(timezone.utc).replace(tzinfo=None) if isinstance(end, datetime) else end
            return await self._ib.reqHistoricalDataAsync(
                c, endDateTime=end_dt, durationStr=BAR_MAP[timeframe][1],
                barSizeSetting=BAR_MAP[timeframe][0], whatToShow="MIDPOINT",
                useRTH=False, formatDate=2)

        bars = self._run(_history())
        return [{"timestamp": b.date.isoformat() if hasattr(b.date, "isoformat") else str(b.date),
                 "open": float(b.open), "high": float(b.high), "low": float(b.low),
                 "close": float(b.close), "volume": float(getattr(b, "volume", 0) or 0),
                 "source": "IBKR", "symbol": "XAUUSD"} for b in bars]

    def quote(self, symbol="XAUUSD") -> dict[str, Any]:
        if symbol.upper().replace("/", "") != "XAUUSD":
            raise ValueError("Adapter limité à XAUUSD")

        async def _quote():
            c = await self._contract()
            ticker = self._ib.reqMktData(c, "", False, False)
            await asyncio.sleep(1.0)
            return {"bid": float(ticker.bid) if ticker.bid is not None else None,
                    "ask": float(ticker.ask) if ticker.ask is not None else None,
                    "mid": float(ticker.marketPrice()) if ticker.marketPrice() is not None else None,
                    "source": "IBKR"}
        return self._run(_quote())

    def account_summary(self):
        async def _summary():
            await self._ensure()
            return await self._ib.accountSummaryAsync()
        return [{"account": x.account, "tag": x.tag, "value": x.value, "currency": x.currency}
                for x in self._run(_summary())]

    def what_if_market(self, side: str, quantity: float):
        async def _what_if():
            from ib_async import MarketOrder
            c = await self._contract()
            order = MarketOrder(side.upper(), quantity)
            order.whatIf = True
            trade = self._ib.placeOrder(c, order)
            await asyncio.sleep(1.0)
            s = trade.orderState
            return {"status": trade.orderStatus.status,
                    "initMarginChange": getattr(s, "initMarginChange", None),
                    "maintMarginChange": getattr(s, "maintMarginChange", None),
                    "commission": getattr(s, "commission", None),
                    "warningText": getattr(s, "warningText", None)}
        return self._run(_what_if())

    def close(self):
        async def _close():
            if self._ib.isConnected():
                self._ib.disconnect()
        self._run(_close())
        self._loop.call_soon_threadsafe(self._loop.stop)
