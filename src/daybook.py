"""Journal de bord : trades papier par jour, bilan, et suivi de la fenêtre nuit comparé au backtest."""
from __future__ import annotations

import csv
import io
import json

MODES = ("PAPIER-MANUEL", "PAPIER-NUIT")
REASONS = {"TP2": "TP2 atteint", "SL": "Stop touché", "BE": "Point mort", "SORTIE HEURE FIXE": "Fermeture auto (nuit)",
           "MANUEL": "Fermée à la main", "STOP": "Bouton STOP"}
BACKTEST_PF = 1.18


def _row(t: dict) -> dict:
    return {"opened_at": t["opened_at"], "closed_at": t["closed_at"], "side": t["side"], "lots": t["lots"],
            "entry": t["entry"], "stop": t["stop"], "tp1": t["tp1"], "tp2": t["tp2"],
            "exit": (json.loads(t["fills"] or "[]") or [{}])[-1].get("price"),
            "reason": REASONS.get(t["outcome"], t["outcome"]), "pnl": t["pnl"], "r": t["r"],
            "strategy": "Fenêtre nuit" if t["mode"] == "PAPIER-NUIT" else "Manuel"}


def _summary(rows: list[dict]) -> dict:
    wins = [r["pnl"] for r in rows if r["pnl"] > 0]; losses = [r["pnl"] for r in rows if r["pnl"] < 0]
    return {"trades": len(rows), "wins": len(wins), "losses": len(losses), "pnl": round(sum(r["pnl"] for r in rows), 2),
            "pf": round(sum(wins) / -sum(losses), 2) if losses else None}


def build(journal, day: str | None = None, limit: int = 2000) -> dict:
    trades = [_row(t) for t in journal.rows("trades", limit) if t.get("mode") in MODES and t.get("closed_at")]
    days = sorted({t["closed_at"][:10] for t in trades}, reverse=True)
    day = day or (days[0] if days else None)
    today = [t for t in trades if t["closed_at"][:10] == day]
    night = [t for t in trades if t["strategy"] == "Fenêtre nuit"]
    return {"day": day, "days": days[:30], "trades": today, "summary": _summary(today),
            "night": {**_summary(night), "backtest_pf": BACKTEST_PF,
                      "note": "Comparer au backtest (PF 1,18 sur 12 ans) ; il faut 20 nuits au moins pour juger."}}


def to_csv(journal) -> str:
    rows = [_row(t) for t in journal.rows("trades", 100000) if t.get("mode") in MODES and t.get("closed_at")]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]) if rows else ["closed_at"], delimiter=";")
    w.writeheader(); w.writerows(rows)
    return buf.getvalue()
