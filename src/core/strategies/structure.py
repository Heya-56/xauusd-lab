"""Support/resistance breakout from the prior N closed candles."""
from src.core.contracts import Decision
from src.core.strategies._common import ATR_PARAMS, atr_stop_target
from src.core.strategies.base import ParamSpec, Strategy


class SrBreakout(Strategy):
    strategy_id = "sr_breakout"
    version = "1.0.0"
    name = "Support/resistance breakout"
    description = "BUY on first close above the prior N-bar high; SELL on first close below the prior N-bar low."
    param_specs = (ParamSpec("lookback", int, 20, 5, 200), *ATR_PARAMS)

    def warmup(self):
        return max(self.params["lookback"], self.params["atr_period"]) + 2

    def evaluate(self, series):
        if len(series) < self.warmup():
            return self._no_trade(series, "WARMUP")
        c, n = series.candles, self.params["lookback"]
        i, ts = len(c) - 1, series.last_ts
        prior = c[i - n:i]                         # excludes the decision candle
        res, sup = max(x.high for x in prior), min(x.low for x in prior)
        ev = (self._ev("resistance", res, ts, "level"), self._ev("support", sup, ts, "level"),
              self._ev("close", c[i].close, ts, "candle"), self._ev("prev_close", c[i - 1].close, ts, "candle"))
        up = c[i].close > res and c[i - 1].close <= res
        dn = c[i].close < sup and c[i - 1].close >= sup
        if not (up or dn):
            return self._result(Decision.NO_TRADE, series, ev, ("INSIDE_RANGE",))
        stop, target = atr_stop_target(self, series)
        if stop is None:
            return self._no_trade(series, "ATR_UNAVAILABLE")
        return self._result(Decision.BUY if up else Decision.SELL, series, ev,
                            ("BREAKOUT_UP",) if up else ("BREAKOUT_DOWN",), stop, target)
