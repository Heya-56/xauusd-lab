"""Les 3 agents de stratégie SQL : chaque fichier agents/sql/*.sql est exécuté par QuestDB à chaque
clôture de bougie. La requête renvoie une ligne (bar_ts, action, entry, r, reason) ; le runner en déduit
stop/TP (1R, 2R) et écrit le résultat dans la table `signals`."""
from __future__ import annotations

import re
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[2] / "agents" / "sql"


def load_agents(sql_dir: Path = SQL_DIR) -> dict[str, str]:
    return {p.stem: p.read_text() for p in sorted(sql_dir.glob("*.sql"))}


def render(sql: str, symbol: str, tf: str) -> str:
    for v in (symbol, tf):
        if not re.fullmatch(r"[A-Za-z0-9_]+", v):
            raise ValueError(f"paramètre refusé : {v!r}")
    return sql.replace("{symbol}", symbol).replace("{tf}", tf).strip().rstrip(";")


def to_signal(row: dict | None) -> dict:
    if not row or row.get("action") not in ("BUY", "SELL") or not row.get("r"):
        entry = (row or {}).get("entry")
        return {"action": "NONE", "entry": entry, "reason": (row or {}).get("reason", "Pas de données")}
    e, r = float(row["entry"]), float(row["r"])
    s = 1 if row["action"] == "BUY" else -1
    return {"action": row["action"], "entry": e, "stop_loss": e - s * r, "tp1": e + s * r, "tp2": e + 2 * s * r,
            "reason": row["reason"]}
