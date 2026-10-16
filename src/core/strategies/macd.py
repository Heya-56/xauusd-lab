"""MACD signal-line crossover. Defaults 12/26/9."""
from src.core.contracts import Decision
from src.core.indicators import macd
from src.core.strategies._common import ATR_PARAMS, atr_stop_target
from src.core.strategies.base import ParamSpec, Strategy


class MacdCross(Strategy):
    strategy_id = "macd_cross"
    version = "1.0.0"
    name = "MACD crossover"
    description = "BUY when MACD line crosses above signal with positive histogram; SELL symmetric. Closed candles only."
    param_specs = (
        ParamSpec("fast", int, 12, 2, 50), ParamSpec("slow", int, 26, 5, 200),
        ParamSpec("signal", int, 9, 2, 50), *ATR_PARAMS,
    )

    @classmethod
    def check_relations(cls, p):
        if p["fast"] >= p["slow"]:
            raise ValueError("macd_cross: fast must be < slow")

    def warmup(self):
        return self.params["slow"] + self.params["signal"] + 1

    def evaluate(self, series):
        if len(series) < self.warmup():
            return self._no_trade(series, "WARMUP")
        closes = [c.close for c in series.candles]
        line, sig, hist = macd(closes, self.params["fast"], self.params["slow"], self.params["signal"])
        i, ts = len(closes) - 1, series.last_ts
        if None in (line[i], sig[i], line[i - 1], sig[i - 1]):
            return self._no_trade(series, "WARMUP")
        ev = (self._ev("macd_line", line[i], ts), self._ev("macd_signal", sig[i], ts),
              self._ev("macd_hist", hist[i], ts), self._ev("macd_line_prev", line[i - 1], ts),
              self._ev("macd_signal_prev", sig[i - 1], ts), self._ev("close", closes[i], ts, "candle"))
        up = line[i - 1] <= sig[i - 1] and line[i] > sig[i] and hist[i] > 0
        dn = line[i - 1] >= sig[i - 1] and line[i] < sig[i] and hist[i] < 0
        if not (up or dn):
            return self._result(Decision.NO_TRADE, series, ev, ("NO_CROSS",))
        stop, target = atr_stop_target(self, series)
        if stop is None:
            return self._no_trade(series, "ATR_UNAVAILABLE")
        return self._result(Decision.BUY if up else Decision.SELL, series, ev,
                            ("MACD_CROSS_UP",) if up else ("MACD_CROSS_DOWN",), stop, target,
                            "opposite MACD cross or stop hit")
