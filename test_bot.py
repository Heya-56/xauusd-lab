from bot import atr, crossover_signal, ema, position_size

def test_ema_length():
    values=list(range(1,61))
    result=ema(values,20)
    assert len(result)==60 and result[19] is not None

def test_position_size_cap():
    assert position_size(10000,3000,2995) <= 0.01

def test_flat_market_has_no_signal():
    closes=[100.0]*100
    highs=[101.0]*100
    lows=[99.0]*100
    assert crossover_signal(closes,highs,lows) is None

def test_atr_exists():
    values=[100+i*0.1 for i in range(30)]
    assert atr(values,[v-1 for v in values],values)[-1] is not None
