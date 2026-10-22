import pytest

from src.engine.manual_paper import ManualPaperBook, PaperError
from src.journal import Journal


def test_buy_tp1_breakeven_then_tp2(tmp_path):
    b = ManualPaperBook(Journal(tmp_path / "m.sqlite"))
    with pytest.raises(PaperError):
        b.open("BUY", 0.1, 4120)                 # pas encore de prix
    b.on_tick(4127.0, 4127.2, "t0")
    with pytest.raises(PaperError):
        b.open("BUY", 0.1, 4130)                 # SL du mauvais côté
    v = b.open("BUY", 0.1, 4122.2)               # entrée à l'ask 4127.2, R = 5
    p = v["positions"][0]
    assert p["entry"] == 4127.2 and p["tp1"] == 4132.2 and p["tp2"] == 4137.2
    b.on_tick(4132.3, 4132.5, "t1")              # TP1 touché (au bid)
    p = b.view()["positions"][0]
    assert p["tp1_done"] and p["sl"] == 4127.2 and p["remaining"] == 0.5
    b.on_tick(4137.3, 4137.5, "t2")              # TP2
    v = b.view()
    assert v["positions"] == [] and v["history"][0]["outcome"] == "TP2"
    assert v["account"]["equity"] == pytest.approx(10_000 + 0.05 * 5 * 100 + 0.05 * 10 * 100, abs=0.5)


def test_sell_stop_and_persistence(tmp_path):
    db = tmp_path / "m.sqlite"
    b = ManualPaperBook(Journal(db))
    b.on_tick(4127.0, 4127.2, "t0")
    pid = b.open("SELL", 0.05, 4130, tp1=4125, tp2=4120)["positions"][0]["id"]
    b2 = ManualPaperBook(Journal(db))            # redémarrage : la position est toujours là
    b2.on_tick(4130.0, 4130.1, "t1")             # SL touché (à l'ask)
    assert b2.view()["positions"] == [] and b2.view()["history"][0]["outcome"] == "SL"
    assert pid


def test_api_paper_and_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("XAUUSD_NO_AUTOAPP", "1")
    monkeypatch.setenv("KILL_SWITCH_FILE", str(tmp_path / "STOP"))
    from fastapi.testclient import TestClient
    from src.api import create_app
    app = create_app(db_path=str(tmp_path / "a.sqlite"))
    c = TestClient(app)
    app.state.book.on_tick(4127.0, 4127.2, "t0")
    r = c.post("/api/paper/open", json={"side": "BUY", "lots": 0.02, "sl": 4122})
    assert r.status_code == 200 and len(r.json()["positions"]) == 1
    pid = r.json()["positions"][0]["id"]
    assert c.post("/api/paper/modify", json={"id": pid, "sl": 4124}).json()["positions"][0]["sl"] == 4124
    c.post("/api/kill", json={"engaged": True})
    assert c.get("/api/paper").json()["positions"] == []
    assert c.post("/api/paper/open", json={"side": "BUY", "lots": 0.02, "sl": 4122}).status_code == 423


def test_open_by_distance(tmp_path):
    b = ManualPaperBook(Journal(tmp_path / "d.sqlite"))
    b.on_tick(4127.0, 4127.2, "t0")
    p = b.open("SELL", 0.01, sl_dist=4, r1=1.5, r2=3)["positions"][0]
    assert (p["entry"], p["sl"], p["tp1"], p["tp2"]) == (4127.0, 4131.0, 4121.0, 4115.0)
