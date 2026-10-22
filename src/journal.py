"""Journal SQLite : bougies, signaux, décisions de risque, trades et état du compte papier."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS candles (
  symbol TEXT NOT NULL, timeframe TEXT NOT NULL, ts TEXT NOT NULL,
  open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL DEFAULT 0,
  PRIMARY KEY (symbol, timeframe, ts)
);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, bar_ts TEXT NOT NULL,
  strategy TEXT NOT NULL, action TEXT NOT NULL, entry REAL, stop_loss REAL, tp1 REAL, tp2 REAL,
  reason TEXT, risk_allowed INTEGER, risk_reason TEXT, lots REAL, mode TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT, opened_at TEXT NOT NULL, closed_at TEXT, side TEXT NOT NULL,
  entry REAL NOT NULL, stop REAL NOT NULL, tp1 REAL, tp2 REAL, lots REAL NOT NULL,
  outcome TEXT, pnl REAL, r REAL, fills TEXT, mode TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Journal:
    def __init__(self, path: str | Path = "xauusd_lab.sqlite"):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # --- état clé/valeur (JSON)
    def get(self, key, default=None):
        row = self.conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key, value):
        self.conn.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (key, json.dumps(value)))
        self.conn.commit()

    # --- bougies
    def add_candle(self, symbol, timeframe, c) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?,?,?)",
            (symbol, timeframe, c["ts"], c["open"], c["high"], c["low"], c["close"], c.get("volume", 0)))
        self.conn.commit()
        return cur.rowcount == 1

    def candles(self, symbol, timeframe, limit=500):
        rows = self.conn.execute(
            "SELECT ts,open,high,low,close,volume FROM candles WHERE symbol=? AND timeframe=? ORDER BY ts DESC LIMIT ?",
            (symbol, timeframe, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # --- signaux & trades
    def add_signal(self, bar_ts, strategy, sig, decision, mode):
        self.conn.execute(
            "INSERT INTO signals(created_at,bar_ts,strategy,action,entry,stop_loss,tp1,tp2,reason,risk_allowed,risk_reason,lots,mode)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (now(), bar_ts, strategy, sig.action, sig.entry, sig.stop_loss, sig.tp1, sig.tp2, sig.reason,
             None if decision is None else int(decision.allowed), None if decision is None else decision.reason,
             None if decision is None else decision.size_lots, mode))
        self.conn.commit()

    def add_trade(self, p, mode):
        self.conn.execute(
            "INSERT INTO trades(opened_at,closed_at,side,entry,stop,tp1,tp2,lots,outcome,pnl,r,fills,mode)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.opened_at, p.closed_at, p.side, p.entry, p.initial_stop, p.tp1, p.tp2, p.lots, p.outcome,
             round(p.realized, 2), round(p.r_multiple, 3), json.dumps(p.fills), mode))
        self.conn.commit()

    def rows(self, table, limit=50):
        assert table in {"signals", "trades"}
        return [dict(r) for r in self.conn.execute(f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,))]
