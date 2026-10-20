"""Stratégie de démonstration : croisement EMA20/EMA50, stop 0,5 × ATR14, TP1 = 1R, TP2 = 2R."""
from __future__ import annotations

from src.indicators import atr, ema
from .base import Signal, StrategyCandidate


def crossover_signal(price, ema20, ema50, prev_ema20, prev_ema50, atr14, atr_mult=0.5) -> Signal:
    if not atr14 or atr14 <= 0:
        return Signal("NONE", price, reason="ATR invalide")
    r = atr_mult * atr14
    if prev_ema20 <= prev_ema50 and ema20 > ema50:
        return Signal("BUY", price, price - r, price + r, price + 2 * r, "EMA20 croise au-dessus de EMA50")
    if prev_ema20 >= prev_ema50 and ema20 < ema50:
        return Signal("SELL", price, price + r, price - r, price - 2 * r, "EMA20 croise sous EMA50")
    return Signal("NONE", price, reason="Pas de croisement confirmé")


class EmaCross(StrategyCandidate):
    name = "ema_cross"

    def __init__(self, fast: int = 20, slow: int = 50, atr_period: int = 14, atr_mult: float = 0.5):
        self.fast, self.slow, self.atr_period, self.atr_mult = fast, slow, atr_period, atr_mult
        self.warmup = slow + 1

    def evaluate(self, candles: list[dict]) -> Signal:
        price = candles[-1]["close"]
        if len(candles) < self.warmup:
            return Signal("NONE", price, reason=f"Historique insuffisant ({len(candles)}/{self.warmup} bougies)")
        closes = [c["close"] for c in candles]
        f, s = ema(closes, self.fast), ema(closes, self.slow)
        a = atr(candles, self.atr_period)[-1]
        return crossover_signal(price, f[-1], s[-1], f[-2], s[-2], a, self.atr_mult)
