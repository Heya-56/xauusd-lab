"""Scenario tests of the MT5 scanner logic (Python mirror of HGS_Scanner.mqh)."""
import random

from research.scanner_reference import BUY, NEUTRAL, SELL, SpreadScanner, Tick


def stream(n, *, carry=15.0, drift_per_s=0.0, noise=0.05, shock_at=None, shock=0.0, shock_len=5,
           roll_at=None, roll_jump=0.0, ref_freeze=None, seed=1, spot_spread=0.25, tick_ms=250):
    """Yield (spot_tick, ref_tick) every tick_ms. Basis = carry + drift + noise (+ shock/roll)."""
    rng = random.Random(seed)
    price, ref_t = 2400.0, None
    for i in range(n):
        t = i * tick_ms
        price += rng.gauss(0, 0.15)
        basis = carry + drift_per_s * t / 1000 + rng.gauss(0, noise)
        if roll_at is not None and t >= roll_at:
            basis += roll_jump
        if shock_at is not None and shock_at <= t < shock_at + shock_len * 1000:
            basis += shock
        spot = Tick(t, round(price, 2), round(price + spot_spread, 2))
        ref_mid = price - basis
        if ref_freeze is None or not (ref_freeze[0] <= t < ref_freeze[1]):
            ref_t = Tick(t, round(ref_mid - 0.05, 2), round(ref_mid + 0.05, 2))
        yield spot, ref_t


def run(sc, ticks):
    events, statuses = [], []
    for s, r in ticks:
        sc.evaluate(s, r)
        statuses.append(sc.snap["status"])
        ch = sc.consume_change()
        if ch:
            events.append((s.time_msc, *ch))
    return events, statuses


def test_warmup_is_always_neutral():
    sc = SpreadScanner(window=60)
    events, statuses = run(sc, stream(200))          # 50 s < 60 samples
    assert set(statuses) == {"WARMUP"} and events == []


def test_quiet_market_with_carry_produces_no_false_signals():
    sc = SpreadScanner(window=120)
    events, _ = run(sc, stream(4000, carry=18.0, noise=0.02, seed=3))
    assert len(events) <= 2                          # big constant basis is not a signal


def test_slow_carry_drift_is_absorbed_by_rolling_mean():
    sc = SpreadScanner(window=120)
    events, _ = run(sc, stream(6000, drift_per_s=0.001, noise=0.02, seed=4))
    assert len(events) <= 2


def test_spot_cheap_shock_gives_buy_then_neutral_once():
    sc = SpreadScanner(window=120)
    # basis falls by 1 USD for 5 s: spot cheap vs reference -> BUY, then back to neutral
    events, _ = run(sc, stream(2000, noise=0.02, shock_at=300_000, shock=-1.0, seed=5))
    sig = [(f, t) for _, f, t in events if t != NEUTRAL or f != NEUTRAL]
    assert (NEUTRAL, BUY) in sig and (BUY, NEUTRAL) in sig
    assert sum(1 for f, t in sig if t == BUY) == 1   # hysteresis: no flicker


def test_spot_rich_shock_gives_sell():
    sc = SpreadScanner(window=120)
    events, _ = run(sc, stream(2000, noise=0.02, shock_at=300_000, shock=+1.0, seed=6))
    assert any(t == SELL for _, _, t in events)


def test_frozen_reference_fails_closed():
    sc = SpreadScanner(window=60, max_quote_age_ms=5000)
    events, statuses = run(sc, stream(3000, noise=0.02, ref_freeze=(400_000, 600_000), seed=7))
    frozen = statuses[1620:2380]                     # ticks clearly inside the freeze (+5 s grace)
    assert set(frozen) == {"STALE_REF"}
    assert sc.snap["status"] == "OK"                 # recovers when the feed resumes


def test_contract_roll_known_limitation_then_relearns():
    """A roll jump looks like a deviation until the window re-learns: documented limitation."""
    sc = SpreadScanner(window=120)
    events, _ = run(sc, stream(4000, noise=0.02, roll_at=400_000, roll_jump=-8.0, seed=8))
    after = [e for e in events if e[0] >= 400_000]
    assert after, "roll should trigger a signal (limitation documented in README)"
    assert sc.snap["signal"] == NEUTRAL              # back to neutral once the new level is learned


def test_tick_bursts_do_not_change_sample_rate():
    a = SpreadScanner(window=60)
    b = SpreadScanner(window=60)
    run(a, stream(1000, tick_ms=250, seed=9))
    run(b, stream(4000, tick_ms=62, seed=9))
    assert abs(a.count - b.count) <= 1               # fixed 1 s sampling


def test_bad_quotes_and_params():
    sc = SpreadScanner(window=60)
    sc.evaluate(Tick(0, 2400, 2399), Tick(0, 2385, 2385.1))
    assert sc.snap["status"] == "BAD_QUOTE"
    sc.evaluate(None, None)
    assert sc.snap["status"] == "NO_TICK"
    import pytest
    with pytest.raises(ValueError):
        SpreadScanner(z_entry=1.0, z_exit=1.5)


def test_gates_are_what_prevent_noise_signals():
    """Same quiet stream: without gates, pure Z>2 fires on noise; with gates it stays silent."""
    naive = SpreadScanner(window=120, min_dev_pts=0.0, cost_mult=0.0, confirm_samples=1)
    gated = SpreadScanner(window=120)
    n_naive, _ = run(naive, stream(4000, noise=0.02, seed=3))
    n_gated, _ = run(gated, stream(4000, noise=0.02, seed=3))
    assert len(n_naive) > 10 and len(n_gated) <= 2


def test_mirror_has_same_inputs_as_mql5():
    from pathlib import Path
    mq = (Path(__file__).resolve().parents[1] / "mql5/HinovaGoldScanner/HinovaGoldScanner.mq5").read_text(encoding="utf-8-sig")
    for name in ("InpMinDevPts", "InpCostMult", "InpConfirmSamples", "InpZEntry", "InpZExit", "InpWindow"):
        assert name in mq
