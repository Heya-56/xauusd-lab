"""Normalized OHLC schema (v1.0) and data-quality validation.

Schema — one candle:
    ts       int    UTC epoch seconds of the candle OPEN time
    open     float
    high     float  >= max(open, close)
    low      float  <= min(open, close)
    close    float
    volume   float  optional, >= 0
    spread   float  optional, price units (bid/ask spread at close)

Series metadata (provenance) is mandatory: symbol, instrument_type, timeframe,
source, timezone of the source, retrieval time. A futures series can never be
declared as spot: the instrument_type travels with the data.

Validation fails closed: the first defect makes the series unusable for signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.core.contracts import (OHLC_SCHEMA_VERSION, TIMEFRAME_SECONDS,
                                DataStatus, InstrumentType, content_hash)


@dataclass(frozen=True)
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float | None = None


@dataclass(frozen=True)
class Provenance:
    symbol: str
    instrument_type: InstrumentType
    timeframe: str
    source: str
    source_timezone: str = "UTC"
    retrieved_at: int | None = None
    notes: str = ""


@dataclass
class QualityReport:
    status: DataStatus
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status is DataStatus.VALID


@dataclass(frozen=True)
class CandleSeries:
    provenance: Provenance
    candles: tuple[Candle, ...]
    schema_version: str = OHLC_SCHEMA_VERSION

    def __len__(self) -> int:
        return len(self.candles)

    def upto(self, index: int) -> "CandleSeries":
        """Return a view with candles[0..index] inclusive (no future data)."""
        return CandleSeries(self.provenance, self.candles[: index + 1], self.schema_version)

    def window(self, end_index: int, size: int) -> "CandleSeries":
        """Candles (end_index-size, end_index] — bounded lookback, still no future data."""
        start = max(0, end_index - size + 1)
        return CandleSeries(self.provenance, self.candles[start:end_index + 1], self.schema_version)

    @property
    def last_ts(self) -> int | None:
        return self.candles[-1].ts if self.candles else None

    def data_hash(self) -> str:
        return content_hash({
            "p": [self.provenance.symbol, self.provenance.instrument_type.value,
                  self.provenance.timeframe, self.provenance.source],
            "c": [(c.ts, c.open, c.high, c.low, c.close) for c in self.candles],
        })[:24]


def validate_series(series: CandleSeries, *, now_ts: int | None = None,
                    max_age_seconds: int | None = None,
                    expected_symbol: str | None = None,
                    allowed_instrument_types: tuple[InstrumentType, ...] | None = None,
                    max_gap_bars: int = 0) -> QualityReport:
    """Check identity, ordering, OHLC coherence, gaps and freshness.

    max_gap_bars=0 means any gap larger than one timeframe is accepted only if
    it falls on a weekend (gold markets close). Freshness is checked only when
    both `now_ts` and `max_age_seconds` are given.
    """
    p = series.provenance
    issues: list[str] = []
    if not series.candles:
        return QualityReport(DataStatus.MISSING, ["EMPTY_SERIES"])
    if p.timeframe not in TIMEFRAME_SECONDS:
        return QualityReport(DataStatus.INVALID, [f"UNKNOWN_TIMEFRAME:{p.timeframe}"])
    if expected_symbol and p.symbol != expected_symbol:
        return QualityReport(DataStatus.INVALID, [f"SYMBOL_MISMATCH:{p.symbol}"])
    if allowed_instrument_types and p.instrument_type not in allowed_instrument_types:
        return QualityReport(DataStatus.INVALID, [f"INSTRUMENT_NOT_ALLOWED:{p.instrument_type.value}"])

    step = TIMEFRAME_SECONDS[p.timeframe]
    prev_ts = None
    for i, c in enumerate(series.candles):
        vals = (c.open, c.high, c.low, c.close)
        if any(v is None or v != v or v <= 0 for v in vals):  # None / NaN / non-positive
            issues.append(f"BAD_PRICE@{i}")
            continue
        if c.high < max(c.open, c.close) or c.low > min(c.open, c.close) or c.high < c.low:
            issues.append(f"INCOHERENT_OHLC@{i}")
        # Constant phase: M1..H1 bars are normally on exact multiples; broker H4/D1
        # bars are offset by the broker timezone. Any change of phase is a defect.
        if c.ts % step != series.candles[0].ts % step:
            issues.append(f"MISALIGNED_TS@{i}")
        if prev_ts is not None:
            if c.ts == prev_ts:
                issues.append(f"DUPLICATE_TS@{i}")
            elif c.ts < prev_ts:
                issues.append(f"OUT_OF_ORDER@{i}")
            elif max_gap_bars and (c.ts - prev_ts) > step * max_gap_bars and not _weekend_gap(prev_ts, c.ts):
                issues.append(f"GAP@{i}")
        prev_ts = c.ts
    if issues:
        return QualityReport(DataStatus.INVALID, issues[:20])

    if now_ts is not None and max_age_seconds is not None:
        close_time = series.candles[-1].ts + step
        if now_ts - close_time > max_age_seconds:
            return QualityReport(DataStatus.STALE, [f"STALE:{now_ts - close_time}s"])
        if close_time > now_ts:
            return QualityReport(DataStatus.INVALID, ["LAST_CANDLE_NOT_CLOSED"])
    return QualityReport(DataStatus.VALID)


def _weekend_gap(a: int, b: int) -> bool:
    # Gap spanning Saturday (UTC) is the normal weekly close for gold.
    from datetime import datetime, timezone
    da = datetime.fromtimestamp(a, tz=timezone.utc)
    return (b - a) <= 3 * 86400 and da.weekday() in (4, 5)
