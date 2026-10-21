import asyncio
import json
import os
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from src.agents.questdb import signal_line, to_ns
from src.agents.sql_agents import load_agents, render, to_signal
from src.feeders.replay import bar_to_ticks
from src.strategies.registry import default_registry
from tests.conftest import make_candles

ROOT = Path(__file__).resolve().parents[1]
duckdb = pytest.importorskip("duckdb")


def bars_db(candles):
    con = duckdb.connect()
    con.execute("CREATE TABLE bars(symbol VARCHAR, tf VARCHAR, timestamp TIMESTAMP, open DOUBLE, high DOUBLE,"
                " low DOUBLE, close DOUBLE, volume DOUBLE, ticks BIGINT)")
    con.executemany("INSERT INTO bars VALUES ('XAUUSD','300s',?,?,?,?,?,?,4)",
                    [(datetime.fromisoformat(c["ts"]).replace(tzinfo=None), c["open"], c["high"], c["low"], c["close"], 0.0)
                     for c in candles])
    return con


def run_sql(con, sql):
    cur = con.execute(render(sql, "XAUUSD", "300s"))
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return to_signal(rows[0] if rows else None)


def test_six_agents_registered():
    assert {a.name for a in default_registry().all()} == {"ema_cross", "macd_cross", "rsi_reversion", "scalp_momentum"}
    assert set(load_agents()) == {"sql_bollinger_reversion", "sql_vwap_cross", "sql_range_breakout"}


def test_python_agents_fire_on_history():
    candles = make_candles(3000)
    for agent in default_registry().all():
        if agent.timeframe != 300:
            continue
        actions = {agent.evaluate(candles[: i + 1]).action for i in range(agent.warmup, len(candles), 3)}
        assert actions & {"BUY", "SELL"}, agent.name


def test_sql_agents_run_and_fire():
    candles = make_candles(1500)
    fired = {}
    for name, sql in load_agents().items():
        for n in range(60, len(candles), 7):
            sig = run_sql(bars_db(candles[:n]), sql)
            if sig["action"] != "NONE":
                fired[name] = sig
                break
    assert set(fired) == set(load_agents())
    for s in fired.values():
        sign = 1 if s["action"] == "BUY" else -1
        assert sign * (s["entry"] - s["stop_loss"]) > 0 and sign * (s["tp2"] - s["tp1"]) > 0


def test_sql_breakout_exact():
    candles = make_candles(30)
    for c in candles:
        c.update(high=2651, low=2649, open=2650, close=2650)
    candles[-1].update(close=2660, high=2661)
    sig = run_sql(bars_db(candles), load_agents()["sql_range_breakout"])
    assert sig["action"] == "BUY" and sig["stop_loss"] == pytest.approx(2657) and sig["tp2"] == pytest.approx(2666)


def test_sql_params_injection_refused():
    with pytest.raises(ValueError):
        render("x {symbol}", "XAUUSD'; DROP TABLE bars;--", "300s")


def test_signal_line():
    l = signal_line("ema_cross", "python", "XAUUSD", "2026-01-05T10:00:00+00:00",
                    {"action": "BUY", "entry": 2650, "stop_loss": 2648, "tp1": 2652, "tp2": None, "reason": 'a "b"'})
    assert l == ('signals,agent=ema_cross,lang=python,symbol=XAUUSD,action=BUY '
                 'entry=2650.0,stop_loss=2648.0,tp1=2652.0,reason="a \\"b\\"" 1767607200000000000\n')
    assert to_ns(1767607200000) == 1767607200000000000


def test_bar_to_ticks_rebuilds_bar():
    c = {"ts": "2026-01-05T10:00:00+00:00", "open": 1, "high": 3, "low": 0.5, "close": 2, "volume": 4}
    t = bar_to_ticks(c, spread=0)
    assert [x["bid"] for x in t] == [1, 0.5, 3, 2] and t[-1]["ts"] < to_ns(c["ts"]) // 10**6 + 300_000


# ---------- intégration : bus Rust réel + agents Python + faux QuestDB ----------
BUS_BIN = ROOT / "bus" / "target" / "release" / "bus"


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.mark.skipif(not BUS_BIN.exists(), reason="bus Rust non compilé (cargo build --release dans bus/)")
def test_end_to_end_bus_agents(tmp_path):
    import websockets
    from src.agents.questdb import QuestDB
    from src.agents.runner import AgentHub
    from src.feeders.replay import replay

    received, ilp_port, bus_port = [], _free_port(), _free_port()
    srv = socket.socket(); srv.bind(("127.0.0.1", ilp_port)); srv.listen()

    def ilp_sink():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            buf = []
            received.append(buf)
            threading.Thread(target=lambda c=conn, b=buf: [b.append(d.decode()) for d in iter(lambda: c.recv(65536), b"")], daemon=True).start()
    threading.Thread(target=ilp_sink, daemon=True).start()

    env = {**os.environ, "BUS_ADDR": f"127.0.0.1:{bus_port}", "QUESTDB_ILP": f"127.0.0.1:{ilp_port}", "BUS_TOKEN": "t0k", "BAR_SECONDS": "300"}
    bus = subprocess.Popen([str(BUS_BIN)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    csv_path = tmp_path / "bars.csv"
    candles = make_candles(800)
    csv_path.write_text("time,open,high,low,close,volume\n" + "\n".join(
        f'{c["ts"]},{c["open"]},{c["high"]},{c["low"]},{c["close"]},10' for c in candles))
    try:
        time.sleep(0.5)
        hub = AgentHub("python", QuestDB(ilp=f"127.0.0.1:{ilp_port}", http=""))
        results = []

        async def scenario():
            async with websockets.connect(f"ws://127.0.0.1:{bus_port}/subscribe") as sub:
                async def consume():
                    async for raw in sub:
                        ev = json.loads(raw)
                        if ev["type"] == "bar":
                            results.extend(await hub.on_bar(ev))
                            if ev["ts_ms"] == int(datetime.fromisoformat(candles[-1]["ts"]).timestamp() * 1000):
                                return
                task = asyncio.create_task(consume())
                await replay(str(csv_path), f"ws://127.0.0.1:{bus_port}/publish?token=t0k", 0, 0.3, 300)
                await asyncio.wait_for(task, 20)
        asyncio.run(scenario())
        time.sleep(1.0)
    finally:
        bus.terminate(); srv.close()

    lines = [l for buf in received for l in "".join(buf).splitlines()]
    assert len(results) == 3 * len(candles)
    bars = [l for l in lines if l.startswith("bars,")]
    assert len(bars) == len(candles)
    assert sum(l.startswith("ticks,") for l in lines) >= 4 * len(candles)
    signals = [l for l in lines if l.startswith("signals,")]
    assert len(signals) == 3 * len(candles)
    assert any(("action=BUY" in l or "action=SELL" in l) for l in signals)
