"""Moteur de risque : il a le dernier mot avant tout ordre, papier ou réel."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    size_lots: float = 0.0


def check(config, proposed_risk_pct, open_positions=0):
    """Contrôle simple conservé pour compatibilité."""
    risk = config["risk"]
    if proposed_risk_pct > risk["max_risk_per_trade_pct"]:
        return RiskDecision(False, "risk_per_trade_exceeded")
    if open_positions >= risk["max_open_positions"]:
        return RiskDecision(False, "max_open_positions_reached")
    return RiskDecision(True, "risk_checks_passed")


class RiskManager:
    def __init__(self, cfg: dict):
        r = cfg["risk"]
        inst = cfg.get("instrument", {})
        self.risk_pct = float(r["max_risk_per_trade_pct"])
        self.max_daily_loss_pct = float(r["max_daily_loss_pct"])
        self.max_open = int(r["max_open_positions"])
        self.max_trades_day = int(cfg.get("experiment", {}).get("max_trades_per_day", 99))
        self.max_lots = float(r.get("max_position_lots", 0.01))
        self.contract_size = float(inst.get("contract_size", 100))  # 1 lot XAUUSD = 100 oz
        self.lot_step = float(inst.get("lot_step", 0.01))

    def size(self, equity: float, entry: float, stop: float) -> float:
        dist = abs(entry - stop)
        if equity <= 0 or dist <= 0:
            return 0.0
        lots = equity * self.risk_pct / 100 / (dist * self.contract_size)
        lots = min(lots, self.max_lots)
        return round(int(lots / self.lot_step) * self.lot_step, 4)

    def evaluate(self, *, equity, day_start_equity, realized_today, open_positions, trades_today, entry, stop) -> RiskDecision:
        if open_positions >= self.max_open:
            return RiskDecision(False, "max_open_positions_reached")
        if trades_today >= self.max_trades_day:
            return RiskDecision(False, "max_trades_per_day_reached")
        if day_start_equity > 0 and -realized_today >= day_start_equity * self.max_daily_loss_pct / 100:
            return RiskDecision(False, "max_daily_loss_reached")
        lots = self.size(equity, entry, stop)
        if lots <= 0:
            return RiskDecision(False, "size_below_minimum_lot")
        return RiskDecision(True, "risk_checks_passed", lots)
