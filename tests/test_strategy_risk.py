from src.engine.position import Position
from src.engine.risk import RiskManager
from src.indicators import atr, ema
from src.strategies.ema_cross import EmaCross, crossover_signal


def test_buy_signal():
    s = crossover_signal(2650, 2649, 2648, 2647, 2648, 4)
    assert s.action == "BUY" and s.stop_loss == 2648 and s.tp1 == 2652 and s.tp2 == 2654


def test_sell_and_none():
    assert crossover_signal(2650, 2647, 2648, 2649, 2648, 4).action == "SELL"
    assert crossover_signal(2650, 2648, 2649, 2648, 2649, 4).action == "NONE"
    assert crossover_signal(2650, 2649, 2648, 2647, 2648, 0).action == "NONE"


def test_indicators():
    assert ema([1, 1, 1], 3) == [1, 1, 1]
    rows = [{"high": 2, "low": 1, "close": 1.5}] * 20
    a = atr(rows, 14)
    assert a[12] is None and abs(a[13] - 1) < 1e-9


def test_strategy_warmup(candles):
    assert EmaCross().evaluate(candles[:10]).action == "NONE"


def test_position_tp1_then_breakeven():
    p = Position("BUY", 100, 98, 102, 104, 0.01, "t0", 100, 0)
    p.update({"ts": "t1", "high": 102.5, "low": 99.5, "close": 102})
    assert p.tp1_done and p.stop == 100 and p.is_open and round(p.realized, 2) == 1.0
    p.update({"ts": "t2", "high": 101, "low": 99.9, "close": 100})
    assert not p.is_open and p.outcome == "BE" and round(p.r_multiple, 2) == 0.5


def test_position_stop_first_when_ambiguous():
    p = Position("SELL", 100, 102, 98, 96, 0.01, "t0", 100, 0)
    p.update({"ts": "t1", "high": 102.1, "low": 97, "close": 100})
    assert p.outcome == "SL" and round(p.r_multiple, 2) == -1.0


def test_risk_manager(cfg):
    rm = RiskManager(cfg)
    assert rm.size(10_000, 2650, 2648) == 0.01  # plafonné
    d = rm.evaluate(equity=10_000, day_start_equity=10_000, realized_today=-60, open_positions=0,
                    trades_today=0, entry=2650, stop=2648)
    assert not d.allowed and d.reason == "max_daily_loss_reached"
    d = rm.evaluate(equity=10_000, day_start_equity=10_000, realized_today=0, open_positions=1,
                    trades_today=0, entry=2650, stop=2648)
    assert d.reason == "max_open_positions_reached"


def test_consensus_is_deterministic():
    from src.engine.score import weighted_consensus
    r = weighted_consensus([{"direction": "LONG", "weight": 0.3}, {"direction": "LONG", "weight": 0.2},
                            {"direction": "SHORT", "weight": 0.1}])
    assert r["direction"] == "LONG"
