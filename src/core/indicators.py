"""Deterministic, causal technical indicators (pure Python, no dependencies).

Every function's output at index i depends only on inputs[0..i]. Values not
yet defined during warm-up are None. Tests assert this property by comparing
full-series output with output computed on truncated prefixes.
"""
from __future__ import annotations

from typing import Sequence

Num = float | None


def sma(values: Sequence[float], n: int) -> list[Num]:
    _check_period(n)
    out: list[Num] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(values: Sequence[float], n: int) -> list[Num]:
    """EMA seeded with the SMA of the first n values (standard convention)."""
    _check_period(n)
    out: list[Num] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2.0 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = k * values[i] + (1 - k) * prev
        out[i] = prev
    return out


def macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (line, signal, histogram) lists, None during warm-up."""
    if fast >= slow:
        raise ValueError("fast period must be < slow period")
    ef, es = ema(values, fast), ema(values, slow)
    line: list[Num] = [a - b if a is not None and b is not None else None for a, b in zip(ef, es)]
    start = next((i for i, v in enumerate(line) if v is not None), None)
    sig: list[Num] = [None] * len(values)
    if start is not None:
        tail = ema([v for v in line[start:]], signal)  # type: ignore[arg-type]
        for j, v in enumerate(tail):
            sig[start + j] = v
    hist: list[Num] = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return line, sig, hist


def rsi(values: Sequence[float], n: int = 14) -> list[Num]:
    """Wilder RSI."""
    _check_period(n)
    out: list[Num] = [None] * len(values)
    if len(values) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / n, losses / n
    out[n] = _rsi_val(ag, al)
    for i in range(n + 1, len(values)):
        d = values[i] - values[i - 1]
        ag = (ag * (n - 1) + max(d, 0.0)) / n
        al = (al * (n - 1) + max(-d, 0.0)) / n
        out[i] = _rsi_val(ag, al)
    return out


def true_range(highs, lows, closes) -> list[float]:
    out = []
    for i in range(len(closes)):
        if i == 0:
            out.append(highs[0] - lows[0])
        else:
            pc = closes[i - 1]
            out.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return out


def atr(highs, lows, closes, n: int = 14) -> list[Num]:
    """Wilder ATR."""
    _check_period(n)
    tr = true_range(highs, lows, closes)
    out: list[Num] = [None] * len(tr)
    if len(tr) < n:
        return out
    prev = sum(tr[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(tr)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def confirmed_pivots(highs, lows, left: int = 3, right: int = 3, upto: int | None = None):
    """Swing pivots that are CONFIRMED by index `upto` (inclusive).

    A pivot at bar p is only known at bar p+right. Returns a list of dicts
    {kind, index, confirmed_at, price}. Pivots needing bars after `upto`
    are excluded, which prevents look-ahead/repainting.
    """
    if left < 1 or right < 1:
        raise ValueError("left/right must be >= 1")
    last = len(highs) - 1 if upto is None else upto
    out = []
    for p in range(left, last - right + 1):
        win_h = highs[p - left:p + right + 1]
        win_l = lows[p - left:p + right + 1]
        if highs[p] == max(win_h) and win_h.count(highs[p]) == 1:
            out.append({"kind": "high", "index": p, "confirmed_at": p + right, "price": highs[p]})
        if lows[p] == min(win_l) and win_l.count(lows[p]) == 1:
            out.append({"kind": "low", "index": p, "confirmed_at": p + right, "price": lows[p]})
    return out


def _rsi_val(ag: float, al: float) -> float:
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def _check_period(n: int) -> None:
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"period must be a positive int, got {n!r}")
