import os

from src.data.csv_adapter import CsvAdapter
from src.engine.backtest import run_backtest
from src.engine.paper import PaperTrader
from src.journal import Journal
from src.strategies.ema_cross import EmaCross


def test_backtest_runs_with_costs(cfg, candles):
    res = run_backtest(candles, EmaCross(), cfg)
    assert res["all"]["trades"] > 0
    assert res["in_sample"]["trades"] + res["out_of_sample"]["trades"] == res["all"]["trades"]
    assert all(t["lots"] <= 0.01 for t in res["trades"])
    cfg2 = {**cfg, "costs": {"spread": 0, "slippage": 0}}
    assert run_backtest(candles, EmaCross(), cfg2)["all"]["net_pnl"] > res["all"]["net_pnl"]


def test_session_filter_blocks_entries(cfg, candles):
    cfg["experiment"]["days"] = ["SAT"]
    cfg["experiment"]["entry_window"] = ["03:00", "03:05"]
    assert run_backtest(candles, EmaCross(), cfg)["all"]["trades"] <= 2


def test_paper_matches_backtest(cfg, candles, tmp_path):
    t = PaperTrader(cfg, EmaCross(), Journal(tmp_path / "p.sqlite"))
    for c in candles:
        t.on_candle(c)
    assert t.on_candle(candles[-1])["status"] == "duplicate"
    bt = run_backtest(candles, EmaCross(), cfg)
    closed = t.j.rows("trades", 10_000)
    assert len(closed) >= bt["all"]["trades"] - 1


def test_csv_mt5_format(tmp_path):
    f = tmp_path / "mt5.csv"
    f.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\n"
                 "2026.01.05\t10:05:00\t2651\t2652\t2650\t2651.5\t10\n"
                 "2026.01.05\t10:00:00\t2650\t2651\t2649\t2651\t12\n")
    rows = CsvAdapter(f).candles()
    assert rows[0]["ts"].startswith("2026-01-05T10:00") and rows[1]["close"] == 2651.5


def test_webhook(tmp_path, candles, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("XAUUSD_NO_AUTOAPP", "1")
    from fastapi.testclient import TestClient
    from src.api import create_app
    client = TestClient(create_app(db_path=str(tmp_path / "w.sqlite")))
    c = candles[0]
    body = {"symbol": "OANDA:XAUUSD", "time": c["ts"], "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]}
    assert client.post("/webhook/tradingview", json={**body, "secret": "bad"}).status_code == 401
    r = client.post("/webhook/tradingview", json={**body, "secret": "s3cret"})
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert client.get("/api/status").json()["mode"] == "PAPER"


def test_consensus_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("XAUUSD_NO_AUTOAPP", "1")
    from fastapi.testclient import TestClient
    from src.agents import questdb
    from src.api import create_app
    rows = [{"agent": a, "action": act, "timestamp": "2026-01-05T10:00:00.000000Z"} for a, act in
            [("ema_cross", "BUY"), ("macd_cross", "BUY"), ("rsi_reversion", "NONE"),
             ("sql_bollinger_reversion", "SELL"), ("sql_vwap_cross", "BUY"), ("sql_range_breakout", "NONE")]]
    monkeypatch.setattr(questdb.QuestDB, "query", lambda self, sql: rows)
    r = TestClient(create_app(db_path=str(tmp_path / "c.sqlite"))).get("/api/consensus").json()
    assert r["agents"] == 6 and r["direction"] == "LONG" and r["score"] == 0.5


def test_kill_switch(tmp_path, monkeypatch, cfg, candles):
    monkeypatch.setenv("KILL_SWITCH_FILE", str(tmp_path / "STOP"))
    monkeypatch.setenv("ADMIN_TOKEN", "adm")
    monkeypatch.setenv("XAUUSD_NO_AUTOAPP", "1")
    from fastapi.testclient import TestClient
    from src import killswitch
    from src.api import create_app
    c = TestClient(create_app(db_path=str(tmp_path / "k.sqlite")))
    assert c.post("/api/kill", json={"engaged": True, "reason": "test"}).json()["engaged"] is True
    t = PaperTrader(cfg, EmaCross(), Journal(tmp_path / "p.sqlite"))
    assert t.on_candle(candles[0])["status"] == "halted"
    assert c.post("/api/kill", json={"engaged": False}).status_code == 401
    assert c.post("/api/kill", json={"engaged": False}, headers={"X-Admin-Token": "adm"}).json()["engaged"] is False
    assert not killswitch.engaged()
