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


def bar_lines(symbol: str, tf_s: int, rates, point: float) -> str:
    """Bougies MT5 (copy_rates) -> lignes ILP de la table `bars`, même format que le bus Rust.
    Les horodatages restent à l'heure du serveur MT5, comme les ticks en direct."""
    out = []
    for r in rates:
        t, o, h, l, c = int(r["time"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
        vol = float(r["tick_volume"]); spread = float(r["spread"]) * point
        out.append(f"bars,symbol={symbol},tf={tf_s}s open={o},high={h},low={l},close={c},volume={vol},"
                   f"ticks={int(vol)}i,spread={spread} {t * 1_000_000_000}\n")
    return "".join(out)


def backfill(mt5, symbol: str, counts=((60, 5000), (300, 20000))) -> None:
    """Charge l'historique M1 / M5 de MT5 dans QuestDB au démarrage : agents et baromètre
    disposent tout de suite de ~2 mois d'historique au lieu de devoir l'accumuler en direct."""
    from src.agents.questdb import QuestDB
    db = QuestDB()
    for sql in ("ALTER TABLE bars DEDUP ENABLE UPSERT KEYS(timestamp, symbol, tf)",):
        try:
            db.query(sql)       # évite les doublons si on recharge plusieurs fois
        except Exception:
            pass                # table pas encore créée : elle le sera par l'écriture ci-dessous
    point = mt5.symbol_info(symbol).point
    tfs = {60: mt5.TIMEFRAME_M1, 300: mt5.TIMEFRAME_M5}
    for tf_s, n in counts:
        rates = mt5.copy_rates_from_pos(symbol, tfs[tf_s], 1, n)   # 1 = on saute la bougie en cours
        if rates is None or len(rates) == 0:
            print(f"Historique {tf_s}s indisponible : {mt5.last_error()}")
            continue
        lines = bar_lines(symbol, tf_s, rates, point)
        for i in range(0, len(lines), 2_000_000):
            db.write(lines[i:i + 2_000_000])
        print(f"Historique chargé dans QuestDB : {len(rates)} bougies {tf_s}s")
    try:
        db.query("ALTER TABLE bars DEDUP ENABLE UPSERT KEYS(timestamp, symbol, tf)")
    except Exception:
        pass


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
    p.add_argument("--backfill-only", action="store_true",
                   help="charge l'historique MT5 dans QuestDB puis s'arrête (processus séparé du flux direct)")
    a = p.parse_args()
    if a.backfill_only:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            raise SystemExit(f"MT5 non initialisé : {mt5.last_error()}")
        mt5.symbol_select(a.symbol, True)
        print("Chargement de l'historique MT5 -> QuestDB ...")
        backfill(mt5, a.symbol)
        print("Terminé. Cette fenêtre peut être fermée.")
        raise SystemExit(0)
    if os.getenv("BUS_TOKEN") and "token=" not in a.url:
        a.url += ("&" if "?" in a.url else "?") + "token=" + os.environ["BUS_TOKEN"]
    asyncio.run(stream(a.symbol, a.url, a.poll))
