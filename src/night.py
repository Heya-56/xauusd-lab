"""Plan « Fenêtre nuit » : seule stratégie validée sur 12 ans de données FxPro (2015-2026, H1).

Règles testées (spread réel + swap FxPro, mercredi exclu à cause du swap x3) :
  entrée  : achat vers 20:50 UTC les nuits de lundi, mardi et jeudi
  sortie  : 07:00 UTC le lendemain (le reste de la position)
  SL      : 5 x ATR H1 (stop d'urgence : un stop serré détruit l'avantage)
  TP1     : 3 x ATR H1, 50 % fermés puis stop au point mort
  TP2     : 6 x ATR H1
  spread  : on n'entre pas au-delà de 0,30 $
Résultat du test : PF 1,18, 9 années positives sur 12. Information seulement, aucun ordre.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

ENTRY_DAYS = (0, 1, 3)              # lundi, mardi, jeudi (UTC)
ENTRY_UTC, EXIT_UTC = (20, 50), (7, 0)
SL_ATR, TP1_ATR, TP2_ATR = 5.0, 3.0, 6.0
MAX_SPREAD = 0.30
STATS = "Testé sur 12 ans (FxPro 2015-2026) : PF 1,18 avec SL/TP, 9 années positives sur 12. Avantage modeste, aucune garantie."


def window(now: datetime | None = None) -> dict:
    """Fenêtre en cours ou prochaine : {open, start, end} en UTC."""
    now = now or datetime.now(timezone.utc)
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for k in range(-1, 8):
        day = base + timedelta(days=k)
        if day.weekday() not in ENTRY_DAYS:
            continue
        start = day.replace(hour=ENTRY_UTC[0], minute=ENTRY_UTC[1])
        end = (day + timedelta(days=1)).replace(hour=EXIT_UTC[0], minute=EXIT_UTC[1])
        if start <= now < end:
            return {"open": True, "start": start, "end": end}
        if now < start:
            return {"open": False, "start": start, "end": end}
    return {"open": False, "start": None, "end": None}


def atr(bars: list[dict], n: int = 24) -> float | None:
    """ATR simple sur des bougies H1 {high, low, close}, plus anciennes d'abord."""
    if len(bars) < n + 1:
        return None
    trs = [max(b["high"] - b["low"], abs(b["high"] - p["close"]), abs(b["low"] - p["close"]))
           for p, b in zip(bars[:-1], bars[1:])]
    return sum(trs[-n:]) / n


def plan(bid: float | None, ask: float | None, h1_bars: list[dict], capital: float = 10_000.0,
         risk_pct: float = 1.0, now: datetime | None = None) -> dict:
    w = window(now)
    a = atr(h1_bars)
    out = {"window": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in w.items()},
           "stats": STATS, "max_spread": MAX_SPREAD, "ready": False}
    if a is None or ask is None or bid is None:
        out["reason"] = "Historique ou prix indisponible"
        return out
    entry = ask
    sl, tp1, tp2 = entry - SL_ATR * a, entry + TP1_ATR * a, entry + TP2_ATR * a
    risk_per_lot = (entry - sl) * 100              # 1 lot = 100 onces
    lots = max(0.01, round(capital * risk_pct / 100 / risk_per_lot, 2))
    spread = ask - bid
    out.update(ready=True, atr=round(a, 2), entry=round(entry, 2), sl=round(sl, 2), tp1=round(tp1, 2),
               tp2=round(tp2, 2), spread=round(spread, 2), spread_ok=spread <= MAX_SPREAD, lots=lots,
               risk_usd=round(lots * risk_per_lot, 2), capital=capital, risk_pct=risk_pct)
    return out
