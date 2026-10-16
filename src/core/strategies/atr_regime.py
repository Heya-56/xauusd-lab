"""ATR volatility regime FILTER. Never proposes a trade; can only block."""
from src.core.contracts import Decision
from src.core.strategies.base import ParamSpec, Strategy


class AtrRegime(Strategy):
    strategy_id = "atr_regime"
    version = "1.0.0"
    name = "ATR volatility regime"
    description = "Blocks signals when ATR/close is outside the configured band (too quiet or too violent)."
    role = "filter"
    param_specs = (
        ParamSpec("period", int, 14, 5, 100),
        ParamSpec("min_atr_pct", float, 0.02, 0.0, 5.0, "Min ATR as % of close"),
        ParamSpec("max_atr_pct", float, 1.5, 0.01, 20.0, "Max ATR as % of close"),
    )

    @classmethod
    def check_relations(cls, p):
        if p["min_atr_pct"] >= p["max_atr_pct"]:
            raise ValueError("atr_regime: min must be < max")

    def warmup(self):
        return self.params["period"] + 1

    def evaluate(self, series):
        if len(series) < self.warmup():
            return self._no_trade(series, "FILTER_BLOCK_WARMUP")
        a = self._atr_last(series, self.params["period"])
        close, ts = series.candles[-1].close, series.last_ts
        pct = 100.0 * a / close
        ev = (self._ev("atr", a, ts), self._ev("atr_pct", pct, ts))
        if pct < self.params["min_atr_pct"]:
            return self._result(Decision.NO_TRADE, series, ev, ("FILTER_BLOCK_LOW_VOL",))
        if pct > self.params["max_atr_pct"]:
            return self._result(Decision.NO_TRADE, series, ev, ("FILTER_BLOCK_HIGH_VOL",))
        return self._result(Decision.NO_TRADE, series, ev, ("FILTER_PASS",))
