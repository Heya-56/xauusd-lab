from datetime import datetime, timezone
from src import night


def bars(n=40, base=4000.0, rng=10.0):
    return [{"high": base + rng / 2, "low": base - rng / 2, "close": base} for _ in range(n)]


def test_window_days():
    mon = datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc)      # lundi soir : ouverte
    wed = datetime(2026, 10, 28, 21, 0, tzinfo=timezone.utc)      # mercredi soir : fermée (swap x3)
    assert night.window(mon)["open"] is True
    assert night.window(wed)["open"] is False
    assert night.window(wed)["start"].weekday() == 3


def test_plan_levels_and_size():
    p = night.plan(3999.8, 4000.0, bars(), capital=10_000, risk_pct=1.0,
                   now=datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc))
    assert p["ready"] and p["atr"] == 10.0
    assert p["sl"] == 3950.0 and p["tp1"] == 4030.0 and p["tp2"] == 4060.0
    assert p["lots"] == 0.02 and p["spread_ok"]          # 100 $ / (50 $ x 100 onces) = 0,02 lot


def test_plan_wide_spread_flagged():
    p = night.plan(3999.0, 4000.0, bars())
    assert p["spread_ok"] is False
