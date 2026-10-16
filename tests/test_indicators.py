import pytest

from src.core.indicators import atr, confirmed_pivots, ema, macd, rsi, sma


def test_sma_and_ema_known_values():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    e = ema([1, 2, 3, 4], 2)
    assert e[0] is None and e[1] == 1.5 and abs(e[2] - 2.5) < 1e-12 and abs(e[3] - 3.5) < 1e-12


def test_rsi_extremes():
    assert rsi(list(range(1, 30)), 14)[-1] == 100.0
    assert rsi(list(range(30, 1, -1)), 14)[-1] == 0.0
    assert rsi([5.0] * 20, 14)[-1] == 50.0


def test_macd_requires_fast_lt_slow():
    with pytest.raises(ValueError):
        macd([1.0] * 50, 26, 12, 9)


@pytest.mark.parametrize("bad", [0, -1, 1.5, None])
def test_invalid_periods_rejected(bad):
    with pytest.raises(ValueError):
        ema([1.0, 2.0], bad)


def test_indicators_are_causal(series):
    """Value at i must not change when later candles are appended."""
    c = series.candles
    closes = [x.close for x in c]
    hs, ls = [x.high for x in c], [x.low for x in c]
    full = (ema(closes, 20), rsi(closes, 14), macd(closes)[2], atr(hs, ls, closes, 14))
    for cut in (60, 150, 333):
        part = (ema(closes[:cut], 20), rsi(closes[:cut], 14), macd(closes[:cut])[2],
                atr(hs[:cut], ls[:cut], closes[:cut], 14))
        for f, p in zip(full, part):
            assert f[:cut] == p


def test_pivots_only_confirmed_and_never_repaint(series):
    c = series.candles
    hs, ls = [x.high for x in c], [x.low for x in c]
    for upto in (100, 250, 400):
        piv = confirmed_pivots(hs, ls, 5, 5, upto=upto)
        assert all(p["confirmed_at"] <= upto for p in piv)
        # Truncating the data after `upto` yields exactly the same pivots.
        assert piv == confirmed_pivots(hs[:upto + 1], ls[:upto + 1], 5, 5)
