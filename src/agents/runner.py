"""Processus agents : s'abonne au bus Rust (WebSocket), et à chaque bougie clôturée
fait calculer les agents puis écrit leurs signaux dans QuestDB.

  python -m src.agents.runner python   # les 3 agents Python
  python -m src.agents.runner sql      # les 3 agents SQL (exécutés par QuestDB)
  python -m src.agents.runner all      # les 6

Variables : BUS_URL (ws://127.0.0.1:9100/subscribe), QUESTDB_ILP (localhost:9009), QUESTDB_HTTP (http://127.0.0.1:9000),
            SQL_DELAY_S (délai avant requête SQL, le temps que QuestDB valide la bougie, défaut 1.5).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone

import websockets

from src.agents.questdb import QuestDB, signal_line
from src.agents.sql_agents import load_agents, render, to_signal
from src.strategies.registry import default_registry

log = logging.getLogger("agents")
HISTORY = 600


def bar_to_candle(ev: dict) -> dict:
    ts = datetime.fromtimestamp(ev["ts_ms"] / 1000, tz=timezone.utc).isoformat()
    return {"ts": ts, **{k: ev[k] for k in ("open", "high", "low", "close", "volume")}}


class AgentHub:
    def __init__(self, mode: str, db: QuestDB):
        self.db = db
        self.py = default_registry().all() if mode in ("python", "all") else []
        self.sql = load_agents() if mode in ("sql", "all") else {}
        self.history: dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY))
        self.sql_delay = float(os.getenv("SQL_DELAY_S", "1.5"))

    def warmup(self, symbol="XAUUSD", tf="300s"):
        if not self.py:
            return
        try:
            bars = self.db.recent_bars(symbol, tf, HISTORY)
            self.history[symbol].extend(bars)
            log.info("préchargement : %d bougies %s depuis QuestDB", len(bars), symbol)
        except Exception as e:  # QuestDB pas encore prêt : on démarre à froid
            log.warning("préchargement impossible (%s) — démarrage à froid", e)

    def run_python(self, symbol: str, candle: dict) -> list[dict]:
        h = self.history[symbol]
        h.append(candle)
        candles = list(h)
        out = []
        for agent in self.py:
            sig = agent.evaluate(candles).to_dict()
            out.append({"agent": agent.name, "lang": "python", **sig})
            self.db.write(signal_line(agent.name, "python", symbol, candle["ts"], sig))
        return out

    def run_sql(self, symbol: str, tf: str, bar_ts: str) -> list[dict]:
        out = []
        for name, sql in self.sql.items():
            try:
                rows = self.db.query(render(sql, symbol, tf))
                sig = to_signal(rows[0] if rows else None)
            except Exception as e:
                log.error("agent SQL %s : %s", name, e)
                continue
            out.append({"agent": name, "lang": "sql", **sig})
            self.db.write(signal_line(name, "sql", symbol, bar_ts, sig))
        return out

    async def on_bar(self, ev: dict) -> list[dict]:
        candle, symbol, tf = bar_to_candle(ev), ev["symbol"], f"{ev['tf_s']}s"
        results = self.run_python(symbol, candle) if self.py else []
        if self.sql:
            await asyncio.sleep(self.sql_delay)
            results += await asyncio.to_thread(self.run_sql, symbol, tf, candle["ts"])
        for r in results:
            if r["action"] != "NONE":
                log.info("%s %-24s %s @ %s — %s", candle["ts"], r["agent"], r["action"], r["entry"], r["reason"])
        return results


async def main(mode: str):
    url = os.getenv("BUS_URL", "ws://127.0.0.1:9100/subscribe")
    hub = AgentHub(mode, QuestDB())
    hub.warmup()
    log.info("agents %s : %s", mode, [a.name for a in hub.py] + list(hub.sql))
    while True:
        try:
            async with websockets.connect(url, max_size=2**22) as ws:
                log.info("connecté au bus %s", url)
                async for raw in ws:
                    ev = json.loads(raw)
                    if ev.get("type") == "bar":
                        await hub.on_bar(ev)
        except (OSError, websockets.ConnectionClosed) as e:
            log.warning("bus indisponible (%s) — nouvelle tentative dans 3 s", e)
            await asyncio.sleep(3)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "all"))
