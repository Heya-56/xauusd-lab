from dataclasses import dataclass

@dataclass
class RiskDecision:
    allowed: bool
    reason: str

def check(config, proposed_risk_pct, open_positions=0):
    risk=config["risk"]
    if proposed_risk_pct > risk["max_risk_per_trade_pct"]:
        return RiskDecision(False,"risk_per_trade_exceeded")
    if open_positions >= risk["max_open_positions"]:
        return RiskDecision(False,"max_open_positions_reached")
    return RiskDecision(True,"risk_checks_passed")
