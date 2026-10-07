"""Deterministic confluence layer for XAUUSD Lab.

This is not a new trading strategy and does not use AI. It combines independent
strategy votes only after they have been normalized into the same signal shape.
A disagreement produces NO TRADE by default.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

@dataclass(frozen=True)
class Vote:
    source: str
    candidate: str
    side: str
    score: float = 0.0
    tradable: bool = True
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass(frozen=True)
class Decision:
    side: str
    confidence: float
    votes: list[dict]
    reason: str

def decide(votes: Iterable[Vote], min_agreement: int = 2,
           min_score: float = 0.0) -> Decision:
    votes = list(votes)
    valid = [v for v in votes if v.tradable and v.side in ("buy", "sell")
             and v.score >= min_score]
    if not valid:
        return Decision("none", 0.0, [v.to_dict() for v in votes], "no_valid_signal")
    buys = [v for v in valid if v.side == "buy"]
    sells = [v for v in valid if v.side == "sell"]
    if len(buys) >= min_agreement and len(buys) > len(sells):
        chosen = buys
    elif len(sells) >= min_agreement and len(sells) > len(buys):
        chosen = sells
    else:
        return Decision("none", 0.0, [v.to_dict() for v in votes], "insufficient_agreement")
    confidence = sum(v.score for v in chosen) / len(chosen)
    return Decision(chosen[0].side, round(confidence, 4),
                    [v.to_dict() for v in votes], f"{len(chosen)}_agree")

def should_trade(decision: Decision, risk_ok: bool,
                 market_ok: bool, news_ok: bool) -> bool:
    return decision.side in ("buy", "sell") and risk_ok and market_ok and news_ok
