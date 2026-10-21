"""Scan de configurations : synthèse des derniers signaux des agents en « configurations détectées ».

Règle : sur la dernière bougie de chaque unité de temps, une configuration apparaît quand au moins
`min_agree` agents (pondérés) donnent la même direction et qu'aucun agent ne donne la direction opposée.
Entrée / stop = médiane des agents concordants ; TP1 = 1R, TP2 = 2R.
Ce n'est pas un conseil : c'est une lecture des calculs, affichée avec son statut de validation.
"""
from __future__ import annotations

from statistics import median


def levels(side: str, entry: float, stop: float, tp: float | None = None) -> dict:
    """Niveaux SL / TP1 / TP2 d'une position. TP1 = 1R ; TP2 = TP fourni, sinon 2R."""
    s = 1 if side == "BUY" else -1
    r = abs(entry - stop)
    return {"entry": entry, "sl": stop, "tp1": entry + s * r, "tp2": tp if tp else entry + 2 * s * r, "r": r}


def build_scan(rows: list[dict], weights: dict, tf_of: dict, min_agree: float = 2.0) -> list[dict]:
    setups = []
    by_tf: dict[int, list[dict]] = {}
    for r in rows:
        if weights.get(r["agent"], 1.0) <= 0 and tf_of.get(r["agent"], 300) == 300:
            continue
        by_tf.setdefault(tf_of.get(r["agent"], 300), []).append(r)
    for tf, rs in sorted(by_tf.items(), reverse=True):
        last = max(r["timestamp"] for r in rs)
        cur = [r for r in rs if r["timestamp"] == last]
        for side, opp in (("BUY", "SELL"), ("SELL", "BUY")):
            agree = [r for r in cur if r["action"] == side and r.get("entry") and r.get("stop_loss")]
            w = sum(weights.get(r["agent"], 1.0) or 1.0 for r in agree)
            need = 1.0 if tf == 60 else min_agree   # le scalping n'a qu'un agent
            if agree and w >= need and not any(r["action"] == opp for r in cur):
                lv = levels(side, median(r["entry"] for r in agree), median(r["stop_loss"] for r in agree))
                setups.append({"side": side, "tf": tf, "bar_ts": last, "sources": len(agree), "out_of": len(cur),
                               "kind": "SCALP" if tf == 60 else "SWING", **{k: round(v, 2) for k, v in lv.items()}})
    return setups
