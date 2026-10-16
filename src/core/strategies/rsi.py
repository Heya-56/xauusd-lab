"""RSI threshold re-entry (mean reversion). Default period 14, 30/70."""
from src.core.contracts import Decision
from src.core.indicators import rsi
from src.core.strategies._common import ATR_PARAMS, atr_stop_target
from src.core.strategies.base import ParamSpec, Strategy


class RsiReversion(Strategy):
    strategy_id = "rsi_reversion"
    version = "1.0.0"
    name = "RSI re-entry"
    description = "BUY when RSI crosses back above oversold; SELL when it crosses back below overbought."
    param_specs = (
        ParamSpec("period", int, 14, 2, 100),
        ParamSpec("oversold", float, 30.0, 5.0, 45.0),
        ParamSpec("overbought", float, 70.0, 55.0, 95.0), *ATR_PARAMS,
    )

    def warmup(self):
        return self.params["period"] + 2

    def evaluate(self, series):
        if len(series) < self.warmup():
            return self._no_trade(series, "WARMUP")
        closes = [c.close for c in series.candles]
        r = rsi(closes, self.params["period"])
        i, ts = len(closes) - 1, series.last_ts
        if r[i] is None or r[i - 1] is None:
            return self._no_trade(series, "WARMUP")
        ev = (self._ev("rsi", r[i], ts), self._ev("rsi_prev", r[i - 1], ts),
              self._ev("close", closes[i], ts, "candle"))
        lo, hi = self.params["oversold"], self.params["overbought"]
        up = r[i - 1] < lo <= r[i]
        dn = r[i - 1] > hi >= r[i]
        if not (up or dn):
            return self._result(Decision.NO_TRADE, series, ev, ("NO_THRESHOLD_CROSS",))
        stop, target = atr_stop_target(self, series)
        if stop is None:
            return self._no_trade(series, "ATR_UNAVAILABLE")
        return self._result(Decision.BUY if up else Decision.SELL, series, ev,
                            ("RSI_OVERSOLD_EXIT",) if up else ("RSI_OVERBOUGHT_EXIT",), stop, target)
