"""Convert a dukascopy-node CSV export into the lab's normalized OHLC schema v1.0.

Fetch (network job only, never in deterministic CI):
    npx dukascopy-node@1.50.0 -i xauusd -from 2025-10-01 -to now -t m15 -p bid -v -f csv -dir raw/bid
    (same with -p ask -dir raw/ask)
Then:
    python research/import_dukascopy.py raw/bid/<f>.csv data/verified/xauusd_m15_dukascopy.csv --timeframe M15 --ask raw/ask/<f>.csv

Provenance: Dukascopy quotes are a broker/ECN XAUUSD price (spot/CFD-style), NOT COMEX
futures; they are recorded as instrument_type "cfd" with source "dukascopy:xauusd:<side>".
Data is fetched for research and must not be redistributed (do not commit it).
Fails closed: any malformed row aborts the import; nothing is "fixed" silently.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.contracts import TIMEFRAME_SECONDS  # noqa: E402


class ImportError_(ValueError):
    pass


def _read(src: Path, step: int) -> list[tuple]:
    rows = []
    with src.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        need = {"timestamp", "open", "high", "low", "close"}
        if not reader.fieldnames or not need <= set(reader.fieldnames):
            raise ImportError_(f"expected columns {sorted(need)}, got {reader.fieldnames}")
        for n, r in enumerate(reader, start=2):
            try:
                ts_raw = int(float(r["timestamp"]))
                ts = ts_raw // 1000 if ts_raw > 10**11 else ts_raw          # ms -> s
                o, h, l, c = (float(r[k]) for k in ("open", "high", "low", "close"))
                v = float(r.get("volume") or 0.0)
            except (TypeError, ValueError) as exc:
                raise ImportError_(f"line {n}: {exc}") from None
            if ts % step:
                raise ImportError_(f"line {n}: timestamp {ts} not aligned to {step}s timeframe")
            rows.append((ts, o, h, l, c, v))
    if not rows:
        raise ImportError_("empty export")
    return rows


def convert(src: Path, dst: Path, timeframe: str, side: str = "bid", tool_version: str = "unknown",
            ask_src: Path | None = None) -> int:
    """If `ask_src` is given, spread = ask close - bid close per candle (both must align)."""
    if timeframe not in TIMEFRAME_SECONDS:
        raise ImportError_(f"unknown timeframe {timeframe}")
    step = TIMEFRAME_SECONDS[timeframe]
    rows = _read(src, step)
    spreads: dict[int, float] = {}
    if ask_src is not None:
        ask = {r[0]: r[4] for r in _read(ask_src, step)}
        for r in rows:
            if r[0] not in ask:
                raise ImportError_(f"ask series missing candle {r[0]}")
            sp = round(ask[r[0]] - r[4], 5)
            if sp < 0:
                raise ImportError_(f"negative spread at {r[0]}")
            spreads[r[0]] = sp
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", "open", "high", "low", "close", "volume", "spread"])
        for ts, o, h, l, c, v in rows:
            w.writerow([ts, o, h, l, c, v, spreads.get(ts, "")])
    meta = {"symbol": "XAUUSD", "instrument_type": "cfd", "timeframe": timeframe,
            "source": f"dukascopy:xauusd:{side}", "source_timezone": "UTC",
            "retrieved_at": int(time.time()),
            "notes": f"dukascopy-node {tool_version}; {side} prices; "
                     f"{'spread = ask close - bid close' if spreads else 'spread not included'}. "
                     "Research use only, do not redistribute."}
    Path(str(dst) + ".meta.json").write_text(json.dumps(meta, indent=2))
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--timeframe", required=True)
    ap.add_argument("--side", default="bid", choices=["bid", "ask"])
    ap.add_argument("--tool-version", default="unknown")
    ap.add_argument("--ask", default=None, help="matching ask-side export to derive spread")
    a = ap.parse_args()
    n = convert(Path(a.src), Path(a.dst), a.timeframe, a.side, a.tool_version,
                Path(a.ask) if a.ask else None)
    print(f"imported {n} candles -> {a.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
