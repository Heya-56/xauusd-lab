"""S.A.T.A. as an EXTERNAL research candidate (no S.A.T.A. code is copied here).

S.A.T.A. belongs to its author. Until a written licence is signed, it is not vendored
in this repository: it is only used when the package is installed separately AND
explicitly enabled with HINOVA_ENABLE_SATA=1. Otherwise the candidate is registered as
unavailable and can never be enabled (fail closed).

Only S.A.T.A.'s analysis entry point (`sata.strategies.analyze`) is called: no broker,
engine, state or network module is imported. Mapping:
  * our series must have the timeframe of the chosen S.A.T.A. horizon's trigger
    (normal -> M15, swing -> H1, scalping -> M1); higher timeframes are resampled from it,
    keeping CLOSED bars only;
  * side -> BUY/SELL, sl_dist -> stop proposal, target = tp1_r x stop;
  * score below `min_score` -> NO_TRADE (S.A.T.A.'s own profile thresholds are 80-90).
"""
from __future__ import annotations

import os

from src.core.contracts import TIMEFRAME_SECONDS, Decision
from src.core.strategies.base import ParamSpec, Strategy

HORIZONS = ("scalping", "normal", "swing")
METHODS = ("tendance", "smc", "orderblock", "combine", "hybride")
SATA_WINDOW = 260
SATA_MIN_BARS = 210


def _load():
    if os.environ.get("HINOVA_ENABLE_SATA") != "1":
        return None, "LICENSE_PENDING_SATA_DISABLED"
    try:
        from sata import strategies as sata_strategies  # type: ignore
        from sata.indicators import Candle as SataCandle, resample  # type: ignore
    except Exception:
        return None, "SATA_NOT_INSTALLED"
    return (sata_strategies, SataCandle, resample), ""


_MOD, _WHY = _load()


class SataExternal(Strategy):
    strategy_id = "sata_external"
    version = "0.1.0"
    name = "S.A.T.A. (externe, recherche)"
    description = ("Méthodes S.A.T.A. appelées depuis le paquet installé séparément. "
                   "Recherche uniquement, licence en attente.")
    available = _MOD is not None
    unavailable_reason = _WHY
    timeframes = ("M1", "M15", "H1")
    param_specs = (
        ParamSpec("horizon", int, 1, 0, 2, "0=scalping 1=normal 2=swing"),
        ParamSpec("method", int, 0, 0, 4, "0=tendance 1=smc 2=orderblock 3=combine 4=hybride"),
        ParamSpec("min_score", int, 80, 50, 100, "Minimum S.A.T.A. score"),
    )

    def _sp(self):
        return _MOD[0].STRATEGIES[HORIZONS[self.params["horizon"]]]

    def warmup(self):
        if _MOD is None:
            return 10**9
        sp = self._sp()
        ratio = TIMEFRAME_SECONDS[sp.tf_bias] // TIMEFRAME_SECONDS[sp.tf_trigger]
        return (SATA_WINDOW + 2) * ratio

    def evaluate(self, series):
        if _MOD is None:
            raise RuntimeError(f"sata_external unavailable: {_WHY}")
        mod, Candle, resample = _MOD
        sp = self._sp()
        if series.provenance.timeframe != sp.tf_trigger:
            return self._no_trade(series, f"TIMEFRAME_MISMATCH:needs_{sp.tf_trigger}")
        if len(series) < self.warmup():
            return self._no_trade(series, "WARMUP")
        base = [Candle(c.ts, c.open, c.high, c.low, c.close, c.volume) for c in series.candles]
        end = series.last_ts + TIMEFRAME_SECONDS[sp.tf_trigger]
        data = {}
        for tf in set(sp.timeframes):
            sec = TIMEFRAME_SECONDS[tf]
            bars = base if tf == sp.tf_trigger else resample(base, sec)
            closed = [b for b in bars if b.t + sec <= end]          # never a forming higher-TF bar
            data[tf] = closed[-SATA_WINDOW:]
        if min(len(v) for v in data.values()) < SATA_MIN_BARS:
            return self._no_trade(series, "WARMUP")
        method = METHODS[self.params["method"]]
        sig = mod.pick_signal("XAU/USD", data, sp, method, self.params["min_score"], False) \
            if method == "hybride" else mod.analyze("XAU/USD", data, sp, method)
        ts = series.last_ts
        ev = [self._ev("sata_score", int(sig.score), ts, "rule"),
              self._ev("sata_method", method, ts, "rule"),
              self._ev("close", series.candles[-1].close, ts, "candle")]
        if sig.atr:
            ev.append(self._ev("sata_atr", float(sig.atr), ts))
        if not sig.tradable or sig.score < self.params["min_score"]:
            return self._result(Decision.NO_TRADE, series, ev, ("SATA_NO_SIGNAL",))
        stop = round(float(sig.sl_dist), 4)
        return self._result(Decision.BUY if sig.side == "buy" else Decision.SELL, series, ev,
                            (f"SATA_{method.upper()}",), stop, round(stop * sp.tp1_r, 4),
                            "S.A.T.A. stop or opposite signal")
