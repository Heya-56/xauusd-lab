"""Agent de SCALPING (M1) — volontairement agressif, donc risqué.

Entrée : EMA9 croise EMA21 ET la clôture casse le plus haut/bas des 3 bougies précédentes.
Stop : 0,6 × ATR14 (M1) · TP1 1R (50 %) · TP2 2R.
Filtre : aucun signal si le spread moyen de la bougie dépasse 25 % du stop — sinon les frais mangent tout.

⚠ En scalping, spread, slippage et latence décident du résultat. À n'utiliser qu'en papier tant que
les tests sur données du broker, coûts inclus, ne sont pas concluants. Le bouton STOP coupe tout.
"""
from src.indicators import atr, ema
from .base import Signal, StrategyCandidate


class ScalpMomentum(StrategyCandidate):
    name = "scalp_momentum"
    timeframe = 60
    warmup = 30

    def __init__(self, atr_mult: float = 0.6, max_spread_ratio: float = 0.25):
        self.atr_mult, self.max_spread_ratio = atr_mult, max_spread_ratio

    def evaluate(self, candles):
        price = candles[-1]["close"]
        if len(candles) < self.warmup:
            return Signal("NONE", price, reason="Historique insuffisant")
        closes = [c["close"] for c in candles]
        f, s = ema(closes, 9), ema(closes, 21)
        a = atr(candles, 14)[-1]
        if not a:
            return Signal("NONE", price, reason="ATR invalide")
        r = self.atr_mult * a
        spread = candles[-1].get("spread") or 0.0
        if spread > self.max_spread_ratio * r:
            return Signal("NONE", price, reason=f"Spread trop large ({spread:.2f} > {self.max_spread_ratio * r:.2f})")
        hi3 = max(c["high"] for c in candles[-4:-1])
        lo3 = min(c["low"] for c in candles[-4:-1])
        if f[-2] <= s[-2] and f[-1] > s[-1] and price > hi3:
            return Signal("BUY", price, price - r, price + r, price + 2 * r, "Scalp : EMA9>EMA21 + cassure 3 bougies")
        if f[-2] >= s[-2] and f[-1] < s[-1] and price < lo3:
            return Signal("SELL", price, price + r, price - r, price - 2 * r, "Scalp : EMA9<EMA21 + cassure 3 bougies")
        return Signal("NONE", price, reason="Pas d'impulsion")
