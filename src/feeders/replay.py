"""Source de données « replay » : rejoue un CSV de bougies (export MT5/TradingView) sous forme de ticks
vers le bus Rust. Chaque bougie devient 4 ticks : open, high/low (ordre selon la couleur), close.

  python -m src.feeders.replay XAUUSD_M5.csv --speed 0      # le plus vite possible
  python -m src.feeders.replay XAUUSD_M5.csv --speed 0.2    # 0,2 s entre chaque bougie
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime

import websockets

from src.data.csv_adapter import CsvAdapter


def bar_to_ticks(c: dict, spread: float = 0.3, tf_s: int = 300) -> list[dict]:
    t0 = int(datetime.fromisoformat(c["ts"]).timestamp() * 1000)
    path = [c["open"], c["low"], c["high"], c["close"]] if c["close"] >= c["open"] else [c["open"], c["high"], c["low"], c["close"]]
    steps = [0, tf_s * 250, tf_s * 500, tf_s * 1000 - 1]
    vol = c.get("volume", 0) / 4
    return [{"symbol": "XAUUSD", "ts": t0 + s, "bid": p - spread / 2, "ask": p + spread / 2, "volume": vol}
            for p, s in zip(path, steps)]


async def replay(path: str, url: str, speed: float, spread: float, tf_s: int):
    candles = CsvAdapter(path).candles()
    async with websockets.connect(url) as ws:
        for i, c in enumerate(candles):
            await ws.send(json.dumps(bar_to_ticks(c, spread, tf_s)))
            if speed:
                await asyncio.sleep(speed)
            elif i % 200 == 0:
                await asyncio.sleep(0)
        # tick de clôture pour fermer la dernière bougie
        last = bar_to_ticks(candles[-1], spread, tf_s)[-1]
        await ws.send(json.dumps({**last, "ts": last["ts"] + 1}))
        await asyncio.sleep(0.5)
    print(f"{len(candles)} bougies rejouées vers {url}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--url", default=os.getenv("BUS_PUBLISH_URL", "ws://localhost:9100/publish"))
    p.add_argument("--speed", type=float, default=0.0)
    p.add_argument("--spread", type=float, default=0.3)
    p.add_argument("--tf", type=int, default=300)
    a = p.parse_args()
    if os.getenv("BUS_TOKEN") and "token=" not in a.url:
        a.url += ("&" if "?" in a.url else "?") + "token=" + os.environ["BUS_TOKEN"]
    asyncio.run(replay(a.csv, a.url, a.speed, a.spread, a.tf))
