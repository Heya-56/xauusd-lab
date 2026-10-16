"""Fibonacci pullback using CONFIRMED swing pivots only (no repainting).

Up leg: confirmed swing low L followed by confirmed swing high H. BUY when the
current candle trades into the 50%-61.8% retracement zone and closes back above
the 50% level, while the leg is not invalidated (low stays above L). SELL is
symmetric. A pivot is only usable once `right` bars have closed after it.
"""
from src.core.contracts import Decision
from src.core.indicators import confirmed_pivots
from src.core.strategies.base import ParamSpec, Strategy


class FibonacciPullback(Strategy):
    strategy_id = "fibonacci_pullback"
    version = "1.0.0"
    name = "Fibonacci pullback (confirmed pivots)"
    description = "Pullback entry in the 50-61.8% zone of the last confirmed swing leg."
    param_specs = (
        ParamSpec("pivot_left", int, 5, 2, 20), ParamSpec("pivot_right", int, 5, 2, 20),
        ParamSpec("zone_shallow", float, 0.5, 0.236, 0.618),
        ParamSpec("zone_deep", float, 0.618, 0.382, 0.886),
        ParamSpec("stop_level", float, 0.786, 0.618, 1.0),
    )

    @classmethod
    def check_relations(cls, p):
        if not p["zone_shallow"] < p["zone_deep"] < p["stop_level"]:
            raise ValueError("fibonacci_pullback: require shallow < deep < stop_level")

    def warmup(self):
        return 4 * (self.params["pivot_left"] + self.params["pivot_right"])

    def evaluate(self, series):
        if len(series) < self.warmup():
            return self._no_trade(series, "WARMUP")
        c = series.candles
        i, ts = len(c) - 1, series.last_ts
        # Pivots must be confirmed strictly before the decision candle.
        piv = confirmed_pivots([x.high for x in c], [x.low for x in c],
                               self.params["pivot_left"], self.params["pivot_right"], upto=i - 1)
        highs = [p for p in piv if p["kind"] == "high"]
        lows = [p for p in piv if p["kind"] == "low"]
        if not highs or not lows:
            return self._no_trade(series, "NO_CONFIRMED_LEG")
        h, l = highs[-1], lows[-1]
        leg = h["price"] - l["price"]
        if leg <= 0:
            return self._no_trade(series, "INVALID_LEG")
        bar = c[i]
        p = self.params
        ev_base = [self._ev("swing_high", h["price"], c[h["index"]].ts, "pivot"),
                   self._ev("swing_low", l["price"], c[l["index"]].ts, "pivot"),
                   self._ev("close", bar.close, ts, "candle")]
        if l["index"] < h["index"]:  # up leg -> look for long pullback
            shallow = h["price"] - p["zone_shallow"] * leg
            deep = h["price"] - p["zone_deep"] * leg
            stop_px = h["price"] - p["stop_level"] * leg
            if bar.low <= shallow and bar.low >= stop_px and bar.close > shallow and bar.close < h["price"]:
                ev = ev_base + [self._ev("fib_zone_top", shallow, ts), self._ev("fib_zone_bottom", deep, ts)]
                return self._result(Decision.BUY, series, ev, ("FIB_PULLBACK_LONG",),
                                    round(bar.close - stop_px, 4), round(h["price"] - bar.close, 4),
                                    f"close below {round(stop_px, 2)}")
        else:  # down leg -> look for short pullback
            shallow = l["price"] + p["zone_shallow"] * leg
            deep = l["price"] + p["zone_deep"] * leg
            stop_px = l["price"] + p["stop_level"] * leg
            if bar.high >= shallow and bar.high <= stop_px and bar.close < shallow and bar.close > l["price"]:
                ev = ev_base + [self._ev("fib_zone_bottom", shallow, ts), self._ev("fib_zone_top", deep, ts)]
                return self._result(Decision.SELL, series, ev, ("FIB_PULLBACK_SHORT",),
                                    round(stop_px - bar.close, 4), round(bar.close - l["price"], 4),
                                    f"close above {round(stop_px, 2)}")
        return self._result(Decision.NO_TRADE, series, ev_base, ("NOT_IN_ZONE",))
