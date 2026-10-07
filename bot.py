"""Test Création Bot — XAUUSD. No broker execution."""
from dataclasses import dataclass
from typing import Literal

@dataclass
class Signal:
    action: Literal["BUY","SELL","NONE"]
    entry: float
    stop_loss: float|None=None
    tp1: float|None=None
    tp2: float|None=None
    reason: str=""

def crossover_signal(price, ema20, ema50, prev_ema20, prev_ema50, atr14):
    if atr14 <= 0:
        return Signal("NONE", price, reason="Invalid ATR")
    r = 0.5 * atr14
    if prev_ema20 <= prev_ema50 and ema20 > ema50:
        return Signal("BUY",price,price-r,price+r,price+2*r,"EMA20 crossed above EMA50")
    if prev_ema20 >= prev_ema50 and ema20 < ema50:
        return Signal("SELL",price,price+r,price-r,price-2*r,"EMA20 crossed below EMA50")
    return Signal("NONE",price,reason="No confirmed crossover")

def position_size(equity, entry, stop, risk_pct=0.25, max_size=0.01):
    if equity <= 0 or entry <= 0 or stop <= 0: return 0.0
    risk_cash = equity * risk_pct / 100
    distance = abs(entry-stop)
    return round(min(risk_cash/distance, max_size),4)
