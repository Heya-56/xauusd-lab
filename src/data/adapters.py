"""Interchangeable market-data adapters returning normalized CandleSeries.

Adapters never substitute another instrument when a feed fails: they raise
DataUnavailable and the caller must produce DATA_MISSING / NO_TRADE.

Available here (no network, no credentials):
- CsvFileAdapter: a CSV of normalized candles + a mandatory provenance sidecar
  JSON (`<file>.meta.json`). This is how a verified broker/MT5 export enters.
- SyntheticFixtureAdapter: deterministic random walk for tests and pipeline
  self-checks. Always labelled InstrumentType.SYNTHETIC; never market data.

Existing broker adapters (src/data/ibkr_*.py) are preserved untouched.
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

from src.core.contracts import TIMEFRAME_SECONDS, InstrumentType
from src.data.ohlc import Candle, CandleSeries, Provenance


class DataUnavailable(RuntimeError):
    pass


class CandleSource:
    name = "abstract"

    def load(self) -> CandleSeries:  # pragma: no cover - interface
        raise NotImplementedError


class CsvFileAdapter(CandleSource):
    name = "csv"
    REQUIRED_META = ("symbol", "instrument_type", "timeframe", "source")

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> CandleSeries:
        meta_path = self.path.with_suffix(self.path.suffix + ".meta.json")
        if not self.path.exists():
            raise DataUnavailable(f"missing data file: {self.path.name}")
        if not meta_path.exists():
            raise DataUnavailable(f"missing provenance sidecar: {meta_path.name}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        missing = [k for k in self.REQUIRED_META if not meta.get(k)]
        if missing:
            raise DataUnavailable(f"provenance incomplete: {missing}")
        try:
            itype = InstrumentType(meta["instrument_type"])
        except ValueError as exc:
            raise DataUnavailable(f"unknown instrument_type {meta['instrument_type']!r}") from exc
        candles = []
        with self.path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                spread = row.get("spread")
                candles.append(Candle(
                    ts=int(row["ts"]), open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                    spread=float(spread) if spread not in (None, "") else None,
                ))
        prov = Provenance(meta["symbol"], itype, meta["timeframe"], meta["source"],
                          meta.get("source_timezone", "UTC"), meta.get("retrieved_at"),
                          meta.get("notes", ""))
        return CandleSeries(prov, tuple(candles))


class SyntheticFixtureAdapter(CandleSource):
    """Deterministic fixture. NOT market data — labelled as such everywhere."""
    name = "synthetic"

    def __init__(self, *, seed: int = 7, n: int = 600, timeframe: str = "M15",
                 start_ts: int = 1_767_225_600, start_price: float = 2400.0,
                 vol: float = 0.0015, spread: float = 0.30):
        self.seed, self.n, self.timeframe = seed, n, timeframe
        self.start_ts, self.start_price, self.vol, self.spread = start_ts, start_price, vol, spread

    def load(self) -> CandleSeries:
        rng = random.Random(self.seed)
        step = TIMEFRAME_SECONDS[self.timeframe]
        price, out = self.start_price, []
        drift_phase = 0.0
        for i in range(self.n):
            drift_phase += 0.02
            drift = 0.0004 * (1 if (int(drift_phase) % 2 == 0) else -1)
            o = price
            c = max(1.0, o * (1 + drift + rng.gauss(0, self.vol)))
            hi = max(o, c) * (1 + abs(rng.gauss(0, self.vol / 2)))
            lo = min(o, c) * (1 - abs(rng.gauss(0, self.vol / 2)))
            out.append(Candle(self.start_ts + i * step, round(o, 2), round(hi, 2),
                              round(lo, 2), round(c, 2), 100.0, self.spread))
            price = c
        prov = Provenance("XAUUSD", InstrumentType.SYNTHETIC, self.timeframe,
                          f"fixture:synthetic-seed-{self.seed}", "UTC", None,
                          "Synthetic random walk for tests. Not market data.")
        return CandleSeries(prov, tuple(out))
