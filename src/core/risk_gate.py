"""Deterministic risk gate. Independent of strategies and agents.

It receives the *proposed* direction and evaluates hard rules. It can veto any
proposal, even if every strategy and every agent agrees. Its limits come from
the validated profile, which is capped by registry.RISK_CEILINGS; no caller
(dashboard, agent, API body) can pass its own limits in.

`execution_allowed` is hard-wired to False in this milestone: the gate can mark
a setup as risk-eligible for research/paper review, never authorize an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.core.contracts import DataStatus, Decision, RiskResult

LIVE_EXECUTION_ENABLED = False  # deliberately a constant, not configuration


@dataclass(frozen=True)
class AccountState:
    """Non-secret state reported by the client terminal or paper ledger."""
    open_positions: int = 0
    daily_pnl_pct: float = 0.0       # negative = loss
    current_spread: float | None = None


def evaluate_risk(decision: Decision, *, data_status: DataStatus, profile: dict,
                  as_of_ts: int, stop_distance: float | None,
                  account: AccountState, requested_risk_pct: float | None = None) -> RiskResult:
    vetoes: list[str] = []
    limits = profile["risk"]
    if decision is Decision.NO_TRADE:
        return RiskResult(allowed=False, veto_codes=["NO_PROPOSAL"], execution_allowed=False)
    if data_status is not DataStatus.VALID:
        vetoes.append(f"DATA_{data_status.value.upper()}")
    hour = datetime.fromtimestamp(as_of_ts, tz=timezone.utc).hour
    s = profile["session_utc"]
    if not (s["start_hour"] <= hour < s["end_hour"]):
        vetoes.append("OUTSIDE_SESSION")
    if account.current_spread is None:
        vetoes.append("SPREAD_UNKNOWN")
    elif account.current_spread > profile["max_spread"]:
        vetoes.append("SPREAD_TOO_WIDE")
    if stop_distance is None or stop_distance <= 0:
        vetoes.append("NO_VALID_STOP")
    elif account.current_spread is not None and stop_distance < 3 * account.current_spread:
        vetoes.append("STOP_TOO_TIGHT_VS_SPREAD")
    if account.open_positions >= limits["max_open_positions"]:
        vetoes.append("MAX_OPEN_POSITIONS")
    if -account.daily_pnl_pct >= limits["max_daily_loss_pct"]:
        vetoes.append("DAILY_LOSS_LIMIT")
    if requested_risk_pct is not None and requested_risk_pct > limits["max_risk_per_trade_pct"]:
        vetoes.append("RISK_PER_TRADE_EXCEEDED")
    return RiskResult(allowed=not vetoes, veto_codes=vetoes,
                      execution_allowed=False)
