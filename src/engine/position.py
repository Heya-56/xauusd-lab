"""Cycle de vie d'une position : stop, TP1 (50 %), passage au point mort, TP2 (50 %).

Règle prudente : si le stop et un objectif sont touchés dans la même bougie, on considère le stop touché en premier.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Position:
    side: str            # BUY / SELL
    entry: float
    stop: float
    tp1: float
    tp2: float
    lots: float
    opened_at: str
    contract_size: float = 100.0
    cost_per_side: float = 0.0   # spread/2 + slippage, en prix
    remaining: float = 1.0       # fraction encore ouverte
    realized: float = 0.0        # P&L réalisé en devise du compte
    tp1_done: bool = False
    closed_at: str | None = None
    outcome: str | None = None
    fills: list = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def __post_init__(self):
        self.initial_stop = self.stop
        self._initial_risk = abs(self.entry - self.stop) * self.lots * self.contract_size

    def _close_part(self, price: float, fraction: float, ts: str, why: str):
        sign = 1 if self.side == "BUY" else -1
        fill = price - sign * self.cost_per_side
        entry = self.entry + sign * self.cost_per_side
        pnl = sign * (fill - entry) * self.lots * fraction * self.contract_size
        self.realized += pnl
        self.remaining = round(self.remaining - fraction, 10)
        self.fills.append({"ts": ts, "price": round(price, 4), "fraction": fraction, "why": why, "pnl": round(pnl, 2)})
        if self.remaining <= 1e-9:
            self.closed_at, self.outcome = ts, why

    def update(self, bar: dict) -> None:
        if not self.is_open:
            return
        ts, hi, lo = bar["ts"], bar["high"], bar["low"]
        buy = self.side == "BUY"
        hit_sl = lo <= self.stop if buy else hi >= self.stop
        if hit_sl:
            self._close_part(self.stop, self.remaining, ts, "BE" if self.tp1_done else "SL")
            return
        if not self.tp1_done and (hi >= self.tp1 if buy else lo <= self.tp1):
            self._close_part(self.tp1, 0.5, ts, "TP1")
            self.tp1_done = True
            self.stop = self.entry  # point mort sur le reste
        if self.tp1_done and self.is_open and (hi >= self.tp2 if buy else lo <= self.tp2):
            self._close_part(self.tp2, self.remaining, ts, "TP2")

    def force_close(self, price: float, ts: str, why: str = "TIME") -> None:
        if self.is_open:
            self._close_part(price, self.remaining, ts, why)

    @property
    def r_multiple(self) -> float:
        return self.realized / self._initial_risk if self._initial_risk else 0.0
