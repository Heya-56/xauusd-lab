import dataclasses

import pytest

from src.core.contracts import DataStatus, Decision, InstrumentType
from src.core.engine import evaluate
from src.core.registry import ConfigError, validate_config
from src.core.risk_gate import AccountState, evaluate_risk
from src.core.strategies.base import Strategy
from src.data.ohlc import Candle, CandleSeries, validate_series

from conftest import SIGNAL_IDS, cfg

OK = AccountState(current_spread=0.3)


def _first_signal_index(series, config, registry):
    for i in range(100, len(series)):
        rec = evaluate(series.upto(i), config, registry, account=OK, allow_synthetic=True)
        if rec.decision is not Decision.NO_TRADE:
            return i, rec
    raise AssertionError("no signal in fixture")


def test_synthetic_rejected_unless_explicitly_allowed(series, registry):
    rec = evaluate(series, cfg(registry, "macd_cross"), registry, account=OK)
    assert rec.decision is Decision.NO_TRADE and rec.data_status is DataStatus.INVALID


def test_futures_never_accepted_as_xauusd(series, registry):
    fut = CandleSeries(dataclasses.replace(series.provenance, instrument_type=InstrumentType.FUTURES),
                       series.candles)
    rec = evaluate(fut, cfg(registry, "macd_cross"), registry, account=OK, allow_synthetic=True)
    assert rec.decision is Decision.NO_TRADE
    assert any("INSTRUMENT_NOT_ALLOWED" in r for r in rec.reason_codes)


@pytest.mark.parametrize("defect", ["dup", "order", "ohlc", "nan", "empty"])
def test_bad_data_fails_closed(series, registry, defect):
    c = list(series.candles[:200])
    if defect == "dup":
        c[150] = dataclasses.replace(c[150], ts=c[149].ts)
    elif defect == "order":
        c[150], c[151] = c[151], c[150]
    elif defect == "ohlc":
        c[150] = dataclasses.replace(c[150], high=c[150].low - 1)
    elif defect == "nan":
        c[150] = dataclasses.replace(c[150], close=float("nan"))
    elif defect == "empty":
        c = []
    s = CandleSeries(series.provenance, tuple(c))
    assert validate_series(s).status is not DataStatus.VALID
    rec = evaluate(s, cfg(registry, *SIGNAL_IDS), registry, account=OK, allow_synthetic=True)
    assert rec.decision is Decision.NO_TRADE


def test_stale_data_fails_closed(series, registry):
    now = series.last_ts + 900 + 10_000
    rec = evaluate(series, cfg(registry, "macd_cross"), registry, account=OK,
                   allow_synthetic=True, now_ts=now)
    assert rec.data_status is DataStatus.STALE and rec.decision is Decision.NO_TRADE


def test_unclosed_candle_rejected(series):
    q = validate_series(series, now_ts=series.last_ts + 10, max_age_seconds=1800)
    assert q.status is DataStatus.INVALID


def test_no_strategy_enabled_is_no_trade(series, registry):
    rec = evaluate(series, cfg(registry), registry, account=OK, allow_synthetic=True)
    assert rec.decision is Decision.NO_TRADE and "NO_STRATEGY_ENABLED" in rec.reason_codes


def test_signal_found_and_execution_never_allowed(series, registry):
    _, rec = _first_signal_index(series, cfg(registry, "sr_breakout"), registry)
    d = rec.to_dict()
    assert d["decision"] in ("BUY", "SELL")
    assert d["execution_allowed"] is False and "LIVE_EXECUTION_DISABLED" in d["reason_codes"]
    assert d["config_hash"] and d["data_hash"] and d["strategy_results"][0]["strategy_version"]


def test_risk_veto_overrides_unanimous_strategies(series, registry):
    config = cfg(registry, "sr_breakout")
    i, _ = _first_signal_index(series, config, registry)
    for acct, code in [(AccountState(current_spread=5.0), "SPREAD_TOO_WIDE"),
                       (AccountState(current_spread=0.3, open_positions=1), "MAX_OPEN_POSITIONS"),
                       (AccountState(current_spread=0.3, daily_pnl_pct=-1.5), "DAILY_LOSS_LIMIT"),
                       (AccountState(current_spread=None), "SPREAD_UNKNOWN")]:
        rec = evaluate(series.upto(i), config, registry, account=acct, allow_synthetic=True)
        assert rec.decision is Decision.NO_TRADE and code in rec.risk.veto_codes


def test_risk_gate_rejects_excess_requested_risk(series):
    from src.core.registry import load_profiles
    r = evaluate_risk(Decision.BUY, data_status=DataStatus.VALID, profile=load_profiles()["swing"],
                      as_of_ts=series.last_ts, stop_distance=5.0, account=OK, requested_risk_pct=2.0)
    assert not r.allowed and "RISK_PER_TRADE_EXCEEDED" in r.veto_codes and r.execution_allowed is False


def test_conflict_produces_no_trade(series, registry):
    class AlwaysBuy(Strategy):
        strategy_id, version = "t_buy", "1.0.0"
        def warmup(self): return 1
        def evaluate(self, s):
            return self._result(Decision.BUY, s, (self._ev("x", 1.0, s.last_ts),), ("T",), 5.0, 5.0)

    class AlwaysSell(AlwaysBuy):
        strategy_id = "t_sell"
        def evaluate(self, s):
            return self._result(Decision.SELL, s, (self._ev("x", 1.0, s.last_ts),), ("T",), 5.0, 5.0)

    from src.core.registry import StrategyRegistry
    reg = StrategyRegistry((AlwaysBuy, AlwaysSell))
    profiles = {"t": {"timeframes": {"bias": "M15", "setup": "M15", "trigger": "M15"}, "decision_timeframe": "M15",
                      "session_utc": {"start_hour": 0, "end_hour": 24}, "max_data_age_seconds": 999999,
                      "max_spread": 1.0, "costs": {"spread": 0.3, "slippage": 0.1, "commission": 0},
                      "max_holding_bars": 10, "eligible_strategies": ["t_buy", "t_sell"],
                      "risk": {"max_risk_per_trade_pct": 0.25, "max_open_positions": 1, "max_daily_loss_pct": 1.0},
                      "mode": "research"}}
    both = validate_config({"profile": "t", "strategies": {"t_buy": {"enabled": True}, "t_sell": {"enabled": True}}},
                           reg, profiles)
    rec = evaluate(series, both, reg, account=OK, allow_synthetic=True)
    assert rec.decision is Decision.NO_TRADE and any(r.startswith("CONFLICT") for r in rec.reason_codes)
    only_buy = validate_config({"profile": "t", "strategies": {"t_buy": {"enabled": True}}}, reg, profiles)
    assert evaluate(series, only_buy, reg, account=OK, allow_synthetic=True).decision is Decision.BUY


def test_strategy_error_fails_closed(series, registry, monkeypatch):
    from src.core.strategies.macd import MacdCross
    monkeypatch.setattr(MacdCross, "evaluate", lambda self, s: 1 / 0)
    rec = evaluate(series, cfg(registry, "macd_cross", "sr_breakout"), registry, account=OK, allow_synthetic=True)
    assert rec.decision is Decision.NO_TRADE
    assert any(r.startswith("STRATEGY_ERROR:macd_cross") for r in rec.reason_codes)


def test_config_cannot_enable_unavailable_or_ineligible(registry):
    with pytest.raises(ConfigError, match="MQL5_SOURCE_MISSING"):
        validate_config({"profile": "intraday", "strategies": {"sata_mql5_parity": {"enabled": True}}}, registry)
    with pytest.raises(ConfigError, match="not eligible"):
        validate_config({"profile": "scalping", "strategies": {"fibonacci_pullback": {"enabled": True}}}, registry)
    with pytest.raises(ConfigError):
        validate_config({"profile": "intraday", "risk": {"max_risk_per_trade_pct": 50}}, registry)
    with pytest.raises(ConfigError):
        validate_config({"profile": "intraday", "strategies": {"macd_cross": {"enabled": True, "code": "x"}}}, registry)


def test_toggle_changes_config_hash_only(registry):
    a = cfg(registry, "macd_cross")
    b = cfg(registry, "macd_cross", "rsi_reversion")
    assert a.config_hash != b.config_hash
    assert a.config_hash == cfg(registry, "macd_cross").config_hash


def test_broker_phase_accepted_but_phase_change_rejected(series):
    import dataclasses as dc
    shifted = CandleSeries(series.provenance, tuple(dc.replace(c, ts=c.ts + 300) for c in series.candles[:200]))
    assert validate_series(shifted).status is DataStatus.VALID          # constant phase (broker offset)
    broken = list(series.candles[:200])
    broken[100] = dc.replace(broken[100], ts=broken[100].ts + 60)
    assert any(i.startswith("MISALIGNED_TS") for i in validate_series(CandleSeries(series.provenance, tuple(broken))).issues)
