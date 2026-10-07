"""Minimal educational XAUUSD strategy engine. No broker execution."""
from dataclasses import dataclass
from math import floor
from typing import Literal

Side = Literal["LONG", "SHORT"]

@dataclass(frozen=True)
class Signal:
    side: Side
    entry: float
    stop: float
    tp1: float
    tp2: float
    risk_distance: float

def ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None] * len(values)
    m = 2 / (period + 1)
    out = [None] * (period - 1)
    prev = sum(values[:period]) / period
    out.append(prev)
    for value in values[period:]:
        prev = (value - prev) * m + prev
        out.append(prev)
    return out

def true_range(high: float, low: float, previous_close: float | None) -> float:
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))

def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("OHLC arrays must have the same length")
    if len(closes) < period:
        return [None] * len(closes)
    trs = [true_range(highs[i], lows[i], closes[i - 1] if i else None) for i in range(len(closes))]
    out = [None] * (period - 1)
    prev = sum(trs[:period]) / period
    out.append(prev)
    for tr in trs[period:]:
        prev = ((prev * (period - 1)) + tr) / period
        out.append(prev)
    return out

def crossover_signal(closes, highs, lows, stop_atr=0.5):
    if len(closes) < 51:
        return None
    fast, slow, atr14 = ema(closes, 20), ema(closes, 50), atr(highs, lows, closes, 14)
    if any(x is None for x in (fast[-2], fast[-1], slow[-2], slow[-1], atr14[-1])):
        return None
    distance = atr14[-1] * stop_atr
    entry = closes[-1]
    if fast[-2] <= slow[-2] and fast[-1] > slow[-1]:
        return Signal("LONG", entry, entry-distance, entry+distance, entry+2*distance, distance)
    if fast[-2] >= slow[-2] and fast[-1] < slow[-1]:
        return Signal("SHORT", entry, entry+distance, entry-distance, entry-2*distance, distance)
    return None

def position_size(capital, entry, stop, risk_fraction=0.0025, max_lot=0.01, contract_size=100.0):
    """Educational approximation; broker contract specifications vary."""
    if capital <= 0 or abs(entry-stop) <= 0:
        return 0.0
    risk_cash = capital * risk_fraction
    raw_lots = risk_cash / (abs(entry-stop) * contract_size)
    return floor(min(raw_lots, max_lot) * 100) / 100
