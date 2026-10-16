import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from src.api import engine_http as eh
from src.api.engine_http import EngineError, handle, sign, verify

SECRET = "s" * 40
CFG = {"profile": "intraday", "strategies": {"sr_breakout": {"enabled": True}}}


def body_from(series, n=300, itype="cfd"):
    s = series.upto(n)
    return {"config": CFG,
            "provenance": {"symbol": "XAUUSD", "instrument_type": itype, "timeframe": "M15", "source": "mt5:test"},
            "candles": [{"ts": c.ts, "open": c.open, "high": c.high, "low": c.low, "close": c.close, "spread": 0.3}
                        for c in s.candles],
            "account": {"open_positions": 0, "daily_pnl_pct": 0.0, "current_spread": 0.3}}


def test_signature_rules():
    ts, b = str(int(time.time())), b'{"a":1}'
    verify(SECRET, ts, sign(SECRET, ts, b), b)
    for args, code in [((SECRET, ts, "00", b), "BAD_SIGNATURE"),
                       ((SECRET, str(int(time.time()) - 600), sign(SECRET, str(int(time.time()) - 600), b), b), "SIGNATURE_EXPIRED"),
                       ((SECRET, None, None, b), "MISSING_SIGNATURE"),
                       (("short", ts, "x", b), "ENGINE_SECRET_NOT_CONFIGURED"),
                       ((SECRET, ts, sign(SECRET, ts, b), b'{"a":2}'), "BAD_SIGNATURE")]:
        with pytest.raises(EngineError, match=code):
            verify(*args)


def test_evaluate_fresh_data_and_never_executable(series):
    b = body_from(series)
    now = series.candles[300].ts + 900 + 5          # candle 300 just closed
    out = handle("/internal/v1/evaluate", b, now=now)
    assert out["data_status"] == "valid" and out["execution_allowed"] is False
    assert out["schema_version"] == "1.0" and out["config_hash"]


def test_stale_futures_and_bad_input_fail_closed(series):
    assert handle("/internal/v1/evaluate", body_from(series), now=time.time())["decision"] == "NO_TRADE"
    fut = handle("/internal/v1/evaluate", body_from(series, itype="futures"), now=series.candles[300].ts + 905)
    assert fut["decision"] == "NO_TRADE" and fut["data_status"] == "invalid"
    with pytest.raises(EngineError, match="INVALID_CONFIG"):
        handle("/internal/v1/evaluate", body_from(series) | {"config": {"profile": "intraday",
               "strategies": {"sata_mql5_parity": {"enabled": True}}}})
    with pytest.raises(EngineError, match="UNKNOWN_FIELDS"):
        handle("/internal/v1/evaluate", body_from(series) | {"tenant_id": "x"})
    with pytest.raises(EngineError, match="BAD_ACCOUNT_FIELDS"):
        handle("/internal/v1/evaluate", body_from(series) | {"account": {"max_risk": 9}})
    with pytest.raises(EngineError, match="BAD_MARKET_DATA"):
        handle("/internal/v1/evaluate", body_from(series) | {"candles": []})


def test_validate_and_catalog():
    out = handle("/internal/v1/config/validate", {"config": CFG})
    assert out["config_hash"] and out["config"]["strategies"]["sr_breakout"]["atr_period"] == 14
    cat = handle("/internal/v1/catalog", {})
    assert {s["strategy_id"] for s in cat["strategies"]} >= {"macd_cross", "sata_mql5_parity"}
    assert "intraday" in cat["profiles"]


def test_real_socket_server(monkeypatch, series):
    monkeypatch.setenv("HINOVA_ENGINE_SECRET", SECRET)
    srv = eh.ThreadingHTTPServer(("127.0.0.1", 0), eh._Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(path, body, secret=SECRET):
        raw = json.dumps(body).encode()
        ts = str(int(time.time()))
        req = urllib.request.Request(base + path, raw, {"Content-Type": "application/json",
                                     "X-Hinova-Ts": ts, "X-Hinova-Sig": sign(secret, ts, raw)})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        assert post("/internal/v1/catalog", {})[0] == 200
        assert post("/internal/v1/catalog", {}, secret="x" * 40) == (401, {"error": "BAD_SIGNATURE"})
        status, out = post("/internal/v1/evaluate", body_from(series))
        assert status == 200 and out["decision"] == "NO_TRADE" and out["execution_allowed"] is False
    finally:
        srv.shutdown()


def test_engine_accepts_the_shared_ea_payload_fixture():
    from pathlib import Path
    fx = json.loads((Path(__file__).resolve().parents[1] / "mql5/HinovaBridge/payload.example.json").read_text())
    body = {"config": CFG, "provenance": fx["provenance"], "candles": fx["candles"], "account": fx["account"]}
    out = handle("/internal/v1/evaluate", body, now=fx["candles"][-1]["ts"] + 905)
    assert out["data_status"] == "valid"          # schema, alignment, OHLC coherence all accepted
    assert out["decision"] == "NO_TRADE"          # 8 candles < warm-up: fail closed, not an error
