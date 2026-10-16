"""EMA fast/slow crossover (MA20/MA50 benchmark)."""
from src.core.contracts import Decision
from src.core.indicators import ema
from src.core.strategies._common import ATR_PARAMS, atr_stop_target
from src.core.strategies.base import ParamSpec, Strategy


class EmaTrend(Strategy):
    strategy_id = "ema_trend"
    version = "1.0.0"
    name = "EMA trend crossover"
    description = "BUY when fast EMA crosses above slow EMA; SELL symmetric."
    param_specs = (ParamSpec("fast", int, 20, 2, 100), ParamSpec("slow", int, 50, 5, 400), *ATR_PARAMS)

    @classmethod
    def check_relations(cls, p):
        if p["fast"] >= p["slow"]:
            raise ValueError("ema_trend: fast must be < slow")

    def warmup(self):
        return self.params["slow"] + 1

    def evaluate(self, series):
        if len(series) < self.warmup():
            return self._no_trade(series, "WARMUP")
        closes = [c.close for c in series.candles]
        f, s = ema(closes, self.params["fast"]), ema(closes, self.params["slow"])
        i, ts = len(closes) - 1, series.last_ts
        if None in (f[i], s[i], f[i - 1], s[i - 1]):
            return self._no_trade(series, "WARMUP")
        ev = (self._ev("ema_fast", f[i], ts), self._ev("ema_slow", s[i], ts),
              self._ev("ema_fast_prev", f[i - 1], ts), self._ev("ema_slow_prev", s[i - 1], ts))
        up = f[i - 1] <= s[i - 1] and f[i] > s[i]
        dn = f[i - 1] >= s[i - 1] and f[i] < s[i]
        if not (up or dn):
            return self._result(Decision.NO_TRADE, series, ev, ("NO_CROSS",))
        stop, target = atr_stop_target(self, series)
        if stop is None:
            return self._no_trade(series, "ATR_UNAVAILABLE")
        return self._result(Decision.BUY if up else Decision.SELL, series, ev,
                            ("EMA_CROSS_UP",) if up else ("EMA_CROSS_DOWN",), stop, target)
