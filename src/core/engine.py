"""Signal engine: data checks -> filters -> strategies -> aggregation -> risk.

Aggregation rule (documented, versioned as AGGREGATION_RULE):
  * any enabled filter that blocks           -> NO_TRADE (FILTER_BLOCK)
  * any strategy error                        -> NO_TRADE (STRATEGY_ERROR), fail closed
  * BUY/SELL without evidence or valid stop   -> discarded as UNSUPPORTED_SIGNAL
  * both BUY and SELL among valid proposals   -> NO_TRADE (CONFLICT), no invented consensus
  * otherwise the shared direction, if at least `min_agreement` strategies agree
  * the risk gate is applied last and can always veto.
Stop proposal = widest agreeing stop; target = smallest agreeing target.
"""
from __future__ import annotations

from src.core.contracts import (SIGNAL_SCHEMA_VERSION, DataStatus, Decision,
                                InstrumentType, Mode, SignalRecord, StrategyResult)
from src.core.registry import StrategyRegistry, ValidatedConfig
from src.core.risk_gate import AccountState, evaluate_risk
from src.data.ohlc import CandleSeries, validate_series

AGGREGATION_RULE = "agree_no_conflict_v1"
TRADABLE_INSTRUMENTS = (InstrumentType.SPOT, InstrumentType.CFD)


def evaluate(series: CandleSeries, config: ValidatedConfig, registry: StrategyRegistry, *,
             account: AccountState, now_ts: int | None = None, min_agreement: int = 1,
             allow_synthetic: bool = False, symbol: str = "XAUUSD") -> SignalRecord:
    profile = config.profile
    allowed_types = TRADABLE_INSTRUMENTS + ((InstrumentType.SYNTHETIC,) if allow_synthetic else ())
    q = validate_series(series, now_ts=now_ts, max_age_seconds=profile["max_data_age_seconds"],
                        expected_symbol=symbol, allowed_instrument_types=allowed_types)
    reasons: list[str] = ["LIVE_EXECUTION_DISABLED", f"AGGREGATION:{AGGREGATION_RULE}"]
    if series.provenance.instrument_type is InstrumentType.SYNTHETIC:
        reasons.append("SYNTHETIC_FIXTURE_NOT_MARKET_DATA")
    if series.provenance.timeframe != profile["decision_timeframe"]:
        q.status, q.issues = DataStatus.INVALID, q.issues + ["TIMEFRAME_PROFILE_MISMATCH"]

    results: list[StrategyResult] = []
    proposal = Decision.NO_TRADE
    stop = target = None

    if q.status is not DataStatus.VALID:
        reasons += [f"DATA:{i}" for i in q.issues] or [f"DATA:{q.status.value}"]
    elif not config.strategies:
        reasons.append("NO_STRATEGY_ENABLED")
    else:
        proposal, stop, target = _run(series, config, registry, results, reasons, min_agreement)

    as_of = series.last_ts or 0
    risk = evaluate_risk(proposal, data_status=q.status, profile=profile, as_of_ts=as_of,
                         stop_distance=stop, account=account)
    final = proposal if risk.allowed else Decision.NO_TRADE
    if proposal is not Decision.NO_TRADE and not risk.allowed:
        reasons.append(f"RISK_VETO:{proposal.value}")
    mode = profile.get("mode", Mode.RESEARCH.value)
    return SignalRecord(SIGNAL_SCHEMA_VERSION, series.provenance.symbol,
                        series.provenance.instrument_type.value, series.provenance.source,
                        config.profile_name, series.provenance.timeframe, final, q.status, as_of,
                        results, risk, reasons, config.config_hash, series.data_hash(), mode)


def _run(series, config, registry, results, reasons, min_agreement):
    strategies = config.instantiate(registry)
    directional = []
    for strat in strategies:
        if len(series) < strat.warmup():
            reasons.append(f"WARMUP:{strat.strategy_id}")
        try:
            r = strat.evaluate(series)
        except Exception as exc:  # fail closed on any strategy error
            reasons.append(f"STRATEGY_ERROR:{strat.strategy_id}:{type(exc).__name__}")
            return Decision.NO_TRADE, None, None
        results.append(r)
        if strat.role == "filter":
            if not any(c == "FILTER_PASS" for c in r.rationale_codes):
                reasons.append(f"FILTER_BLOCK:{strat.strategy_id}")
            continue
        if r.decision is not Decision.NO_TRADE:
            if not r.evidence or not r.stop_distance or r.stop_distance <= 0:
                reasons.append(f"UNSUPPORTED_SIGNAL:{strat.strategy_id}")
                continue
            directional.append(r)
    if any(x.startswith("FILTER_BLOCK") for x in reasons):
        return Decision.NO_TRADE, None, None
    sides = {r.decision for r in directional}
    if len(sides) > 1:
        reasons.append("CONFLICT:" + ",".join(f"{r.strategy_id}={r.decision.value}" for r in directional))
        return Decision.NO_TRADE, None, None
    if len(directional) < max(1, min_agreement):
        reasons.append("NO_VALID_SIGNAL" if not directional else "INSUFFICIENT_AGREEMENT")
        return Decision.NO_TRADE, None, None
    side = directional[0].decision
    stop = max(r.stop_distance for r in directional)
    targets = [r.target_distance for r in directional if r.target_distance]
    reasons.append(f"AGREE:{len(directional)}")
    return side, stop, (min(targets) if targets else None)
