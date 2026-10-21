import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
import os
os.environ.setdefault("XAUUSD_NO_BUS", "1")


@pytest.fixture
def cfg():
    c = yaml.safe_load((ROOT / "config/experiment.yml").read_text())
    c["experiment"].pop("entry_window", None)
    c["experiment"]["days"] = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    c["experiment"]["max_trades_per_day"] = 10
    return c


def make_candles(n=2000, seed=7, start=2650.0):
    rnd = random.Random(seed)
    t0 = datetime(2026, 1, 5, tzinfo=timezone.utc)
    out, price = [], start
    for i in range(n):
        drift = 1.5 * math.sin(i / 60)
        o = price
        c = o + drift * 0.2 + rnd.gauss(0, 1.2)
        h = max(o, c) + abs(rnd.gauss(0, 0.6))
        l = min(o, c) - abs(rnd.gauss(0, 0.6))
        out.append({"ts": (t0 + timedelta(minutes=5 * i)).isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": 1})
        price = c
    return out


@pytest.fixture
def candles():
    return make_candles()
