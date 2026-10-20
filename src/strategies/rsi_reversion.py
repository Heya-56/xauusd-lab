"""Agent Python n°3 : retour à la moyenne RSI(14) — sortie de zone 30/70, filtrée par EMA200."""
from src.indicators import atr, ema
from .base import Signal, StrategyCandidate


def rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(closes)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


class RsiReversion(StrategyCandidate):
    name = "rsi_reversion"
    warmup = 201

    def __init__(self, low=30, high=70, atr_mult=1.0):
        self.low, self.high, self.atr_mult = low, high, atr_mult

    def evaluate(self, candles):
        price = candles[-1]["close"]
        if len(candles) < self.warmup:
            return Signal("NONE", price, reason="Historique insuffisant")
        closes = [c["close"] for c in candles]
        r_ = rsi(closes)
        trend = ema(closes, 200)[-1]
        a = atr(candles, 14)[-1]
        if not a or r_[-2] is None:
            return Signal("NONE", price, reason="Indicateurs indisponibles")
        r = self.atr_mult * a
        if r_[-2] < self.low <= r_[-1] and price > trend:
            return Signal("BUY", price, price - r, price + r, price + 2 * r, f"RSI ressort de survente ({r_[-1]:.1f})")
        if r_[-2] > self.high >= r_[-1] and price < trend:
            return Signal("SELL", price, price + r, price - r, price - 2 * r, f"RSI ressort de surachat ({r_[-1]:.1f})")
        return Signal("NONE", price, reason=f"RSI {r_[-1]:.1f}")
