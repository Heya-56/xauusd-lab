"""Source de données MetaTrader 5 (Windows, terminal MT5 ouvert et connecté au broker).
Lit les ticks en continu et les publie sur le bus Rust ; lit aussi (sans jamais les modifier)
les positions ouvertes pour les afficher sur le graphique avec SL / TP1 / TP2.

  pip install MetaTrader5 websockets
  python -m src.feeders.mt5 --symbol XAUUSD --url ws://IP_DU_BUS:9100/publish
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os


def send_positions(api: str, items: list) -> None:
    import urllib.request
    req = urllib.request.Request(f"{api}/api/positions", data=json.dumps({"positions": items}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=2).read()
    except OSError:
        pass  # API pas lancée : les prix continuent d'aller au bus


async def stream(symbol: str, url: str, poll: float):
    import MetaTrader5 as mt5  # disponible uniquement sous Windows
    import websockets

    if not mt5.initialize():
        raise SystemExit(f"MT5 non initialisé : {mt5.last_error()}")
    if not mt5.symbol_select(symbol, True):
        raise SystemExit(f"Symbole introuvable chez le broker : {symbol}")
    last_ms, last_pos = 0, 0.0
    api = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
    async with websockets.connect(url, proxy=None) as ws:
        print(f"MT5 → bus : {symbol} vers {url}  ·  positions → {api}/api/positions")
        while True:
            now = asyncio.get_running_loop().time()
            if now - last_pos >= 1.0:   # positions ouvertes, lecture seule, 1×/seconde
                last_pos = now
                pos = mt5.positions_get(symbol=symbol) or ()
                await asyncio.to_thread(send_positions, api, [
                    {"ticket": p.ticket, "symbol": p.symbol, "type": p.type, "volume": p.volume,
                     "price_open": p.price_open, "sl": p.sl, "tp": p.tp, "price_current": p.price_current,
                     "profit": p.profit, "time": p.time} for p in pos])
            t = mt5.symbol_info_tick(symbol)
            if t and t.time_msc > last_ms:
                last_ms = t.time_msc
                await ws.send(json.dumps({"symbol": symbol, "ts": t.time_msc, "bid": t.bid, "ask": t.ask,
                                          "volume": float(t.volume_real or t.volume or 0)}))
            await asyncio.sleep(poll)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--url", default=os.getenv("BUS_PUBLISH_URL", "ws://127.0.0.1:9100/publish"))
    p.add_argument("--poll", type=float, default=0.05)
    a = p.parse_args()
    if os.getenv("BUS_TOKEN") and "token=" not in a.url:
        a.url += ("&" if "?" in a.url else "?") + "token=" + os.environ["BUS_TOKEN"]
    asyncio.run(stream(a.symbol, a.url, a.poll))
