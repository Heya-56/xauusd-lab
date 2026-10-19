"""Read-only MetaTrader 5 quote bridge to the local Rust event bus."""
from __future__ import annotations
import json, os, time, uuid
from datetime import datetime, timezone
from typing import Any

def normalize_tick(tick: Any, *, symbol: str, venue: str, sequence: int) -> dict[str, Any]:
    timestamp_ms = int(getattr(tick, "time_msc", 0) or 0)
    bid, ask = float(getattr(tick, "bid", 0.0) or 0.0), float(getattr(tick, "ask", 0.0) or 0.0)
    if timestamp_ms <= 0 or bid <= 0 or ask <= 0 or bid > ask:
        raise ValueError("MT5 returned an invalid or incomplete quote")
    return {"schema_version": 1, "event_id": f"mt5-{symbol}-{timestamp_ms}-{sequence}-{uuid.uuid4().hex[:8]}",
            "source": "mt5", "symbol": symbol, "instrument_type": "broker_instrument_unverified",
            "timestamp_ms": timestamp_ms, "received_at_ms": int(time.time()*1000), "sequence": sequence,
            "bid": bid, "ask": ask, "venue": venue or None}

def main() -> int:
    try:
        import MetaTrader5 as mt5
        import websocket
    except ImportError as exc:
        raise SystemExit("Install dependencies on Windows with: py -m pip install -r requirements-mt5.txt") from exc
    endpoint = os.getenv("EVENT_BUS_WS_URL", "ws://127.0.0.1:8787/ws/ingest")
    symbol = os.getenv("MT5_SYMBOL", "XAUUSD").strip()
    poll_seconds = max(0.05, float(os.getenv("MT5_POLL_SECONDS", "0.1")))
    if not symbol: raise SystemExit("MT5_SYMBOL cannot be empty")
    if not (endpoint.startswith("ws://127.0.0.1:") or endpoint.startswith("ws://localhost:")):
        raise SystemExit("Safety check: bridge only permits a loopback event-bus URL")
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}. Open and log in to MT5.")
    try:
        terminal, account = mt5.terminal_info(), mt5.account_info()
        if terminal is None or account is None:
            raise SystemExit("MT5 terminal/account is not ready; log in to the terminal first.")
        if not mt5.symbol_select(symbol, True):
            raise SystemExit(f"Cannot select {symbol!r} in MT5 Market Watch: {mt5.last_error()}")
        if mt5.symbol_info(symbol) is None: raise SystemExit(f"No MT5 metadata for symbol {symbol!r}")
        venue = str(getattr(account, "server", "") or "")
        print(f"Read-only MT5 bridge for {symbol}; server={venue or 'unknown'}; endpoint={endpoint}. No orders will be sent.", flush=True)
        sequence, last_time_msc = 0, -1
        with websocket.create_connection(endpoint, timeout=5) as ws:
            while True:
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    print(f"No tick yet for {symbol}; MT5 error={mt5.last_error()}", flush=True)
                    time.sleep(poll_seconds); continue
                tick_time = int(getattr(tick, "time_msc", 0) or 0)
                if tick_time > last_time_msc:
                    sequence += 1
                    payload = normalize_tick(tick, symbol=symbol, venue=venue, sequence=sequence)
                    ws.send(json.dumps(payload, separators=(",", ":")))
                    ack = json.loads(ws.recv())
                    if not ack.get("ok"): raise RuntimeError(f"Rust event bus rejected MT5 tick: {ack}")
                    last_time_msc = tick_time
                    print(f"{datetime.fromtimestamp(tick_time/1000, tz=timezone.utc).isoformat()} {symbol} bid={payload['bid']} ask={payload['ask']} ack={ack.get('event_id')}", flush=True)
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("MT5 bridge stopped.", flush=True); return 0
    finally: mt5.shutdown()

if __name__ == "__main__": raise SystemExit(main())
