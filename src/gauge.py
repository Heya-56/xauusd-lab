"""Baromètre court / moyen / long terme.

Pour chaque horizon, 7 indicateurs « d'état » votent en continu (+1 achat, -1 vente, 0 neutre) :
  tendance  : prix vs EMA20, EMA20 vs EMA50
  momentum  : histogramme MACD, RSI14 (>55 / <45), variation sur 10 bougies
  position  : place du prix dans les bandes de Bollinger (20, 2) et dans le range des 20 dernières bougies
Le score (-100…+100) est la moyenne des votes. La « chance » affichée n'est pas inventée : c'est la part
des situations passées de même niveau de score où le prix était plus haut (ou plus bas) N bougies après.
"""
from __future__ import annotations

from src.indicators import ema
from src.strategies.rsi_reversion import rsi

HORIZONS = [
    {"key": "court", "label": "COURT TERME", "tf": "M5", "sample": None, "ahead": 12, "ahead_label": "1 h"},
    {"key": "moyen", "label": "MOYEN TERME", "tf": "H1", "sample": "1h", "ahead": 8, "ahead_label": "8 h"},
    {"key": "long", "label": "LONG TERME", "tf": "H4", "sample": "4h", "ahead": 6, "ahead_label": "24 h"},
]
NAMES = ["Prix / EMA20", "EMA20 / EMA50", "MACD", "RSI 14", "Momentum 10", "Bollinger", "Range 20"]
BUCKETS = [(-1.01, -0.5), (-0.5, -0.15), (-0.15, 0.15), (0.15, 0.5), (0.5, 1.01)]


def votes_series(closes: list[float], highs: list[float], lows: list[float]) -> list[list[int] | None]:
    """Votes des 7 indicateurs pour chaque bougie (None tant que l'historique est insuffisant)."""
    n = len(closes)
    e20, e50 = ema(closes, 20), ema(closes, 50)
    macd = [a - b for a, b in zip(ema(closes, 12), ema(closes, 26))]
    sig = ema(macd, 9)
    r = rsi(closes, 14)
    out: list[list[int] | None] = []
    for i in range(n):
        if i < 50 or r[i] is None:
            out.append(None)
            continue
        c = closes[i]
        w = closes[i - 19:i + 1]
        mean = sum(w) / 20
        sd = (sum((x - mean) ** 2 for x in w) / 19) ** 0.5
        hi, lo = max(highs[i - 19:i + 1]), min(lows[i - 19:i + 1])
        roc = c - closes[i - 10]
        z = (c - mean) / sd if sd else 0
        pos = (c - lo) / (hi - lo) if hi > lo else .5
        sgn = lambda x, eps=0.0: 1 if x > eps else -1 if x < -eps else 0
        out.append([
            sgn(c - e20[i]), sgn(e20[i] - e50[i]), sgn(macd[i] - sig[i]),
            1 if r[i] > 55 else -1 if r[i] < 45 else 0,
            sgn(roc), 1 if z > 0.5 else -1 if z < -0.5 else 0,
            1 if pos > 0.66 else -1 if pos < 0.33 else 0,
        ])
    return out


def label(score: float) -> str:
    if score >= 50: return "ACHAT FORT"
    if score >= 15: return "ACHAT"
    if score > -15: return "NEUTRE"
    if score > -50: return "VENTE"
    return "VENTE FORTE"


def evaluate(bars: list[dict], ahead: int) -> dict:
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    vs = votes_series(closes, highs, lows)
    if not vs or vs[-1] is None:
        return {"ready": False, "bars": len(bars), "need": 51}
    scores = [None if v is None else sum(v) / len(v) for v in vs]
    cur = scores[-1]
    b_lo, b_hi = next(b for b in BUCKETS if b[0] <= cur < b[1])
    up = down = flat = 0
    for i in range(len(scores) - ahead):
        s = scores[i]
        if s is None or not (b_lo <= s < b_hi):
            continue
        d = closes[i + ahead] - closes[i]
        up += d > 0; down += d < 0; flat += d == 0
    n = up + down + flat
    return {
        "ready": True, "score": round(cur * 100), "verdict": label(cur * 100),
        "votes": [{"name": nm, "vote": v} for nm, v in zip(NAMES, vs[-1])],
        "prob_up": round(100 * up / n) if n else None, "prob_down": round(100 * down / n) if n else None,
        "sample": n, "reliable": n >= 100, "bars": len(bars),
    }


def gauge(fetch_bars) -> dict:
    """fetch_bars(sample) -> bougies M5 brutes (sample=None) ou regroupées (sample='1h'/'4h')."""
    out = []
    for h in HORIZONS:
        try:
            res = evaluate(fetch_bars(h["sample"]), h["ahead"])
        except Exception as e:  # données indisponibles
            res = {"ready": False, "error": str(e)}
        out.append({**{k: h[k] for k in ("key", "label", "tf", "ahead_label")}, **res})
    return {"horizons": out,
            "note": "Lecture des indicateurs, pas un conseil. Les chances sont mesurées sur l'historique "
                    "de GOLD chargé dans QuestDB ; elles ne garantissent rien pour la suite."}
