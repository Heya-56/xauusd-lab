"""Accès QuestDB : écriture ILP (TCP 9009) et requêtes SQL (HTTP 9000 /exec). Bibliothèque standard uniquement."""
from __future__ import annotations

import json
import os
import socket
import urllib.parse
import urllib.request
from datetime import datetime


def _tag(v: str) -> str:
    return "".join("_" if c in ' ,=\\\n' else c for c in str(v))


def _str(v: str) -> str:
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def to_ns(ts) -> int:
    if isinstance(ts, (int, float)):
        return int(ts * 1_000_000) if ts > 1e11 else int(ts * 1_000_000_000)
    return int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp() * 1_000_000_000)


def signal_line(agent: str, lang: str, symbol: str, bar_ts, sig: dict) -> str:
    """Une ligne ILP pour la table `signals`, horodatée à l'ouverture de la bougie évaluée."""
    tags = f"signals,agent={_tag(agent)},lang={_tag(lang)},symbol={_tag(symbol)},action={_tag(sig['action'])}"
    fields = [f"{k}={float(sig[k])}" for k in ("entry", "stop_loss", "tp1", "tp2") if sig.get(k) is not None]
    fields.append(f"reason={_str(sig.get('reason', ''))}")
    return f"{tags} {','.join(fields)} {to_ns(bar_ts)}\n"


class QuestDB:
    def __init__(self, ilp: str | None = None, http: str | None = None):
        self.ilp = ilp if ilp is not None else os.getenv("QUESTDB_ILP", "127.0.0.1:9009")
        self.http = (http if http is not None else os.getenv("QUESTDB_HTTP", "http://127.0.0.1:9000")).rstrip("/")
        self._sock = None

    def write(self, lines: str) -> None:
        if not self.ilp:
            return
        for attempt in (1, 2):
            try:
                if self._sock is None:
                    host, port = self.ilp.rsplit(":", 1)
                    self._sock = socket.create_connection((host, int(port)), timeout=5)
                self._sock.sendall(lines.encode())
                return
            except OSError:
                self._sock = None
                if attempt == 2:
                    raise

    def query(self, sql: str) -> list[dict]:
        url = f"{self.http}/exec?" + urllib.parse.urlencode({"query": sql})
        with urllib.request.urlopen(url, timeout=15) as r:
            res = json.loads(r.read().decode())
        if "error" in res:
            raise RuntimeError(f"QuestDB : {res['error']}")
        cols = [c["name"] for c in res.get("columns", [])]
        return [dict(zip(cols, row)) for row in res.get("dataset", [])]

    def recent_bars(self, symbol="XAUUSD", tf="300s", limit=500) -> list[dict]:
        rows = self.query(f"SELECT timestamp, open, high, low, close, volume FROM bars "
                          f"WHERE symbol = '{_tag(symbol)}' AND tf = '{_tag(tf)}' ORDER BY timestamp DESC LIMIT {int(limit)}")
        return [{"ts": r["timestamp"], **{k: r[k] for k in ("open", "high", "low", "close", "volume")}} for r in reversed(rows)]
