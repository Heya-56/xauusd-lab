"""Agent Python n°2 : croisement MACD(12,26,9) dans le sens de l'histogramme, stop 1 × ATR14."""
from src.indicators import atr, ema
from .base import Signal, StrategyCandidate


class MacdCross(StrategyCandidate):
    name = "macd_cross"
    warmup = 40

    def __init__(self, atr_mult: float = 1.0):
        self.atr_mult = atr_mult

    def evaluate(self, candles):
        price = candles[-1]["close"]
        if len(candles) < self.warmup:
            return Signal("NONE", price, reason="Historique insuffisant")
        closes = [c["close"] for c in candles]
        line = [a - b for a, b in zip(ema(closes, 12), ema(closes, 26))]
        sig = ema(line, 9)
        a = atr(candles, 14)[-1]
        if not a:
            return Signal("NONE", price, reason="ATR invalide")
        r = self.atr_mult * a
        if line[-2] <= sig[-2] and line[-1] > sig[-1] and line[-1] - sig[-1] > 0:
            return Signal("BUY", price, price - r, price + r, price + 2 * r, "MACD croise au-dessus du signal")
        if line[-2] >= sig[-2] and line[-1] < sig[-1]:
            return Signal("SELL", price, price + r, price - r, price - 2 * r, "MACD croise sous le signal")
        return Signal("NONE", price, reason="Pas de croisement MACD")
