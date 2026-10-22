"""Indicateurs techniques en Python pur (aucune dépendance)."""
from __future__ import annotations


def ema(values: list[float], n: int) -> list[float]:
    k = 2 / (n + 1)
    out, prev = [], None
    for v in values:
        prev = v if prev is None else k * v + (1 - k) * prev
        out.append(prev)
    return out


def atr(rows: list[dict], n: int = 14) -> list[float | None]:
    """ATR de Wilder. None tant que la fenêtre n'est pas remplie."""
    out: list[float | None] = [None] * len(rows)
    tr = []
    for i, r in enumerate(rows):
        if i == 0:
            tr.append(r["high"] - r["low"])
        else:
            pc = rows[i - 1]["close"]
            tr.append(max(r["high"] - r["low"], abs(r["high"] - pc), abs(r["low"] - pc)))
        if i == n - 1:
            out[i] = sum(tr) / n
        elif i >= n:
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out
