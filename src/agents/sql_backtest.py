"""Permet de backtester les agents SQL hors QuestDB : la même requête est exécutée par DuckDB
sur les dernières bougies (syntaxe commune aux deux moteurs)."""
from __future__ import annotations

from datetime import datetime

from src.agents.sql_agents import load_agents, render, to_signal
from src.strategies.base import Signal, StrategyCandidate


class SqlAgentStrategy(StrategyCandidate):
    timeframe = 300
    warmup = 50

    def __init__(self, name: str, sql: str):
        import duckdb
        self.name, self.sql = name, render(sql, "BT", "300s")
        self.con = duckdb.connect()
        self.con.execute("CREATE TABLE bars(symbol VARCHAR, tf VARCHAR, timestamp TIMESTAMP, open DOUBLE, high DOUBLE,"
                         " low DOUBLE, close DOUBLE, volume DOUBLE, ticks BIGINT)")

    def evaluate(self, candles):
        price = candles[-1]["close"]
        if len(candles) < self.warmup:
            return Signal("NONE", price, reason="Historique insuffisant")
        self.con.execute("DELETE FROM bars")
        self.con.executemany("INSERT INTO bars VALUES ('BT','300s',?,?,?,?,?,?,4)", [
            (datetime.fromisoformat(str(c["ts"]).replace("Z", "+00:00")).replace(tzinfo=None),
             c["open"], c["high"], c["low"], c["close"], float(c.get("volume") or 0)) for c in candles[-60:]])
        cur = self.con.execute(self.sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        s = to_signal(rows[0] if rows else None)
        return Signal(s["action"], s.get("entry") or price, s.get("stop_loss"), s.get("tp1"), s.get("tp2"), s.get("reason", ""))


def sql_strategies() -> list[SqlAgentStrategy]:
    try:
        return [SqlAgentStrategy(n, q) for n, q in load_agents().items()]
    except ImportError:
        return []
