import json

import pytest

from src.api.service import ApiError, KeyStore, SignalApi
from src.commercial.entitlements import DAY, grant_plan, has_feature, start_trial
from src.data.queries import QueryError, connect, run_query

NOW = 1_800_000_000


@pytest.fixture
def conn():
    c = connect(":memory:")
    for t in ("tenant_a", "tenant_b"):
        c.execute("INSERT INTO tenants VALUES (?, ?, ?)", (t, t, NOW))
    c.commit()
    return c


def test_only_allow_listed_queries(conn):
    with pytest.raises(QueryError):
        run_query(conn, "SELECT * FROM signal_runs", "tenant_a")
    with pytest.raises(QueryError):
        run_query(conn, "signals.recent", "tenant_a", {"limit": "5; DROP TABLE tenants"})
    with pytest.raises(QueryError):
        run_query(conn, "signals.recent", "tenant_a", {"limit": 5, "tenant_id": "tenant_b"})
    with pytest.raises(QueryError):
        run_query(conn, "config.insert", "tenant_a", {"config_hash": "x", "config_json": "{}",
                  "created_at": 1, "created_by": "u"}, allowed=frozenset({"config.latest"}))


def test_injection_payload_is_inert_data(conn):
    evil = "x'); DROP TABLE tenants; --"
    run_query(conn, "config.insert", "tenant_a", {"config_hash": evil, "config_json": "{}",
              "created_at": NOW, "created_by": "u"})
    assert conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 2


def test_tenant_isolation(conn):
    run_query(conn, "config.insert", "tenant_a", {"config_hash": "ha", "config_json": "{}",
              "created_at": NOW, "created_by": "u"})
    assert run_query(conn, "config.latest", "tenant_b") == []
    assert run_query(conn, "config.latest", "tenant_a")[0]["config_hash"] == "ha"


def test_trial_is_seven_days_once_and_server_clock(conn):
    assert start_trial(conn, "tenant_a", NOW) is True
    assert start_trial(conn, "tenant_a", NOW + 10) is False
    assert has_feature(conn, "tenant_a", "signals.read", NOW + 7 * DAY - 1)
    assert not has_feature(conn, "tenant_a", "signals.read", NOW + 7 * DAY)
    assert has_feature(conn, "tenant_a", "config.write", NOW)          # a trial can configure strategies
    assert not has_feature(conn, "tenant_a", "branding", NOW)
    assert not has_feature(conn, "tenant_b", "signals.read", NOW)
    with pytest.raises(ValueError):
        grant_plan(conn, "tenant_a", "free_forever", NOW, NOW + 1)


# ---------------------------------------------------------------- API
KEY_A, KEY_B = "key-a-0123456789", "key-b-0123456789"


@pytest.fixture
def api(conn, registry):
    for t in ("tenant_a", "tenant_b"):
        grant_plan(conn, t, "subscription", NOW - DAY, NOW + 30 * DAY)
    keys = KeyStore({KeyStore.hash_key(KEY_A): "tenant_a", KeyStore.hash_key(KEY_B): "tenant_b"})
    return SignalApi(conn, keys, registry)


def body(series, **over):
    s = series.upto(300)
    b = {"schema_version": "1.0", "idempotency_key": "idem-0001", "request_ts": NOW,
         "provenance": {"symbol": "XAUUSD", "instrument_type": "cfd", "timeframe": "M15", "source": "mt5:test-broker"},
         "candles": [{"ts": c.ts, "open": c.open, "high": c.high, "low": c.low, "close": c.close} for c in s.candles],
         "account": {"open_positions": 0, "daily_pnl_pct": 0.0, "current_spread": 0.3}}
    b.update(over)
    return b


def test_auth_required(api):
    with pytest.raises(ApiError) as e:
        api.update_config("wrong", {"profile": "intraday"}, now=NOW)
    assert e.value.status == 401


def test_config_then_signal_flow_is_stale_safe(api, series):
    api.update_config(KEY_A, {"profile": "intraday", "strategies": {"macd_cross": {"enabled": True}}}, now=NOW)
    out = api.evaluate(KEY_A, body(series), now=NOW)
    sig = out["signal"]
    assert sig["tenant_id"] == "tenant_a" and sig["execution_allowed"] is False
    # fixture candles are years older than NOW -> stale -> NO_TRADE, never a fabricated signal
    assert sig["decision"] == "NO_TRADE" and sig["data_status"] == "stale"


def test_idempotency_and_replay_protection(api, series):
    api.update_config(KEY_A, {"profile": "intraday", "strategies": {"macd_cross": {"enabled": True}}}, now=NOW)
    first = api.evaluate(KEY_A, body(series), now=NOW)
    again = api.evaluate(KEY_A, body(series), now=NOW + 5)
    assert again["status"] == "replayed" and again["signal"]["signal_id"] == first["signal"]["signal_id"]
    with pytest.raises(ApiError, match="REQUEST_TS_OUT_OF_WINDOW"):
        api.evaluate(KEY_A, body(series, idempotency_key="idem-0002", request_ts=NOW - 3600), now=NOW)


def test_tenant_spoofing_rejected_and_isolated(api, series):
    api.update_config(KEY_A, {"profile": "intraday", "strategies": {"macd_cross": {"enabled": True}}}, now=NOW)
    with pytest.raises(ApiError, match="TENANT_ID_NOT_ACCEPTED"):
        api.evaluate(KEY_B, body(series) | {"tenant_id": "tenant_a"}, now=NOW)
    with pytest.raises(ApiError, match="NO_CONFIG"):          # B cannot use A's config
        api.evaluate(KEY_B, body(series), now=NOW)
    assert run_query(api.conn, "signals.recent", "tenant_b", {"limit": 10}) == []


def test_invalid_inputs_rejected(api, series):
    api.update_config(KEY_A, {"profile": "intraday", "strategies": {"macd_cross": {"enabled": True}}}, now=NOW)
    for bad, code in [(body(series, schema_version="9.9"), "UNSUPPORTED_SCHEMA_VERSION"),
                      (body(series, candles=[]), "CANDLES_COUNT_OUT_OF_RANGE"),
                      (body(series, account={"open_positions": 0, "daily_pnl_pct": 0, "current_spread": 0.3,
                                             "max_risk_override": 9}), "BAD_ACCOUNT_FIELDS"),
                      (body(series, idempotency_key="x"), "BAD_IDEMPOTENCY_KEY")]:
        with pytest.raises(ApiError, match=code):
            api.evaluate(KEY_A, bad, now=NOW)
    with pytest.raises(ApiError, match="INVALID_CONFIG"):
        api.update_config(KEY_A, {"profile": "intraday", "strategies": {"sata_mql5_parity": {"enabled": True}}}, now=NOW)


def test_entitlement_expiry_blocks_api(conn, registry, series):
    start_trial(conn, "tenant_a", NOW)
    api = SignalApi(conn, KeyStore({KeyStore.hash_key(KEY_A): "tenant_a"}), registry)
    api.update_config(KEY_A, {"profile": "intraday"}, now=NOW)
    with pytest.raises(ApiError, match="NOT_ENTITLED:config.write"):
        api.update_config(KEY_A, {"profile": "intraday"}, now=NOW + 8 * DAY)
    with pytest.raises(ApiError, match="NOT_ENTITLED:signals.read"):
        api.evaluate(KEY_A, body(series), now=NOW + 8 * DAY)


def test_audit_events_written(api, series):
    api.update_config(KEY_A, {"profile": "intraday", "strategies": {"macd_cross": {"enabled": True}}}, now=NOW)
    rows = api.conn.execute("SELECT tenant_id, kind, payload_json FROM audit_events").fetchall()
    assert rows and rows[0][0] == "tenant_a" and "config_hash" in json.loads(rows[0][2])
