"""EMA slope + distance momentum.

Idea adapted from "EMASlopeDistanceCocktailXAUUSD" (frontline/units/...) in
https://github.com/zhutoutoutousan/profitable-expert-advisor, commit 982c3ad,
Copyright (c) 2026 Profitable Expert Advisor contributors, MIT License
(see docs/THIRD_PARTY_NOTICES.md). Re-implemented from scratch in Python; no
source code copied.

Original idea: when price is far from its EMA AND the EMA slope is steep, open
in the direction of price relative to the EMA.

Deliberate differences from the original (documented, tested):
  * closed candles only (the original reads the forming bar -> look-ahead in tests)
  * every proposal carries an ATR stop (the original opened with SL = 0)
  * thresholds in price units; defaults derived from the original's H1 set
    (350 points = 3.50 USD distance, 22.5 points = 0.225 USD slope per bar)
  * the weekly ADX filter and "max trades per crossover" are not reproduced
    (no multi-timeframe data in this milestone; the engine allows one position)
"""
from src.core.contracts import Decision
from src.core.indicators import ema
from src.core.strategies._common import ATR_PARAMS, atr_stop_target
from src.core.strategies.base import ParamSpec, Strategy


class EmaSlopeDistance(Strategy):
    strategy_id = "ema_slope_distance"
    version = "1.0.0"
    name = "EMA slope + distance (MIT idea, re-implemented)"
    description = ("Trigger when |close-EMA| and |EMA slope| both exceed thresholds within a short window; "
                   "trade in the direction of close vs EMA. ATR stop always set.")
    timeframes = ("M15", "H1", "H4")
    param_specs = (
        ParamSpec("ema_period", int, 85, 10, 400),
        ParamSpec("distance_threshold", float, 3.5, 0.1, 100.0, "Min |close-EMA| in price units"),
        ParamSpec("slope_threshold", float, 0.225, 0.01, 20.0, "Min |EMA[i]-EMA[i-1]| in price units"),
        ParamSpec("monitor_bars", int, 1, 1, 20, "Bars the trigger stays armed"),
        *ATR_PARAMS,
    )

    def warmup(self):
        return self.params["ema_period"] + self.params["monitor_bars"] + 2

    def evaluate(self, series):
        if len(series) < self.warmup():
            return self._no_trade(series, "WARMUP")
        closes = [c.close for c in series.candles]
        e = ema(closes, self.params["ema_period"])
        i, ts = len(closes) - 1, series.last_ts
        p = self.params
        armed_at = None
        for j in range(i, i - p["monitor_bars"], -1):
            if e[j] is None or e[j - 1] is None:
                continue
            if abs(closes[j] - e[j]) > p["distance_threshold"] and abs(e[j] - e[j - 1]) > p["slope_threshold"]:
                armed_at = j
                break
        ev = [self._ev("ema", e[i], ts), self._ev("ema_prev", e[i - 1], ts),
              self._ev("close", closes[i], ts, "candle"),
              self._ev("distance", closes[i] - e[i], ts), self._ev("slope", e[i] - e[i - 1], ts)]
        if armed_at is None:
            return self._result(Decision.NO_TRADE, series, ev, ("NOT_ARMED",))
        ev.append(self._ev("armed_at_ts", series.candles[armed_at].ts, ts, "rule"))
        if closes[i] == e[i]:
            return self._result(Decision.NO_TRADE, series, ev, ("ON_EMA",))
        stop, target = atr_stop_target(self, series)
        if stop is None:
            return self._no_trade(series, "ATR_UNAVAILABLE")
        up = closes[i] > e[i]
        return self._result(Decision.BUY if up else Decision.SELL, series, ev,
                            ("SLOPE_DISTANCE_UP",) if up else ("SLOPE_DISTANCE_DOWN",), stop, target,
                            "close crosses back through EMA or stop hit")
