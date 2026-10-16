"""API application services (framework-agnostic, no strategy math here).

Routes (to be mounted by a Worker/FastAPI adapter later) call these handlers:
  POST /v1/signals/evaluate  -> SignalApi.evaluate
  PUT  /v1/config            -> SignalApi.update_config
  GET  /v1/strategies        -> SignalApi.catalog

Security properties enforced here:
  * tenant identity derives from the API key, never from the body
  * entitlements checked server-side with the server clock
  * request timestamp window + per-tenant idempotency key (replay protection)
  * strict input validation, bounded payload sizes
  * responses are proposals: execution_allowed is always False
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import uuid

from src.commercial.entitlements import has_feature
from src.core.contracts import SIGNAL_SCHEMA_VERSION, InstrumentType
from src.core.engine import evaluate
from src.core.registry import ConfigError, StrategyRegistry, validate_config
from src.core.risk_gate import AccountState
from src.data.ohlc import Candle, CandleSeries, Provenance
from src.data.queries import run_query

MAX_CANDLES = 2000
REPLAY_WINDOW_SECONDS = 300
BODY_KEYS = {"schema_version", "idempotency_key", "request_ts", "provenance", "candles", "account"}


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


class KeyStore:
    """Maps SHA-256(api_key) -> tenant_id. Raw keys are never stored."""

    def __init__(self, key_hashes: dict[str, str]):
        self._hashes = dict(key_hashes)

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def tenant_for(self, raw_key: str | None) -> str:
        if not raw_key:
            raise ApiError(401, "UNAUTHENTICATED")
        h = self.hash_key(raw_key)
        for stored, tenant in self._hashes.items():
            if hmac.compare_digest(stored, h):
                return tenant
        raise ApiError(401, "UNAUTHENTICATED")


class SignalApi:
    def __init__(self, conn: sqlite3.Connection, keys: KeyStore, registry: StrategyRegistry | None = None):
        self.conn, self.keys = conn, keys
        self.registry = registry or StrategyRegistry()

    # ---- GET /v1/strategies -------------------------------------------
    def catalog(self) -> dict:
        return {"strategies": self.registry.catalog()}

    # ---- PUT /v1/config -----------------------------------------------
    def update_config(self, api_key: str | None, body: dict, *, now: int) -> dict:
        tenant = self.keys.tenant_for(api_key)
        self._require(tenant, "config.write", now)
        try:
            cfg = validate_config(body, self.registry)
        except ConfigError as exc:
            raise ApiError(422, f"INVALID_CONFIG:{exc}") from None
        run_query(self.conn, "config.insert", tenant, {
            "config_hash": cfg.config_hash, "config_json": json.dumps(cfg.to_dict() | {"raw": body}),
            "created_at": now, "created_by": "api_key"})
        self._audit(tenant, "config.updated", {"config_hash": cfg.config_hash}, now)
        return {"status": "stored", "config_hash": cfg.config_hash}

    # ---- POST /v1/signals/evaluate -----------------------------------
    def evaluate(self, api_key: str | None, body: dict, *, now: int) -> dict:
        tenant = self.keys.tenant_for(api_key)
        self._require(tenant, "signals.read", now)
        self._validate_body(body, now)
        prior = run_query(self.conn, "signals.by_idempotency", tenant,
                          {"idempotency_key": body["idempotency_key"]})
        if prior:
            return {"status": "replayed", "signal": json.loads(prior[0]["record_json"])}
        latest = run_query(self.conn, "config.latest", tenant)
        if not latest:
            raise ApiError(409, "NO_CONFIG")
        raw_cfg = json.loads(latest[0]["config_json"])["raw"]
        cfg = validate_config(raw_cfg, self.registry)       # re-validated on every use
        series = self._series(body)
        acct = body["account"]
        record = evaluate(series, cfg, self.registry, now_ts=now, account=AccountState(
            open_positions=int(acct["open_positions"]), daily_pnl_pct=float(acct["daily_pnl_pct"]),
            current_spread=float(acct["current_spread"]) if acct.get("current_spread") is not None else None))
        out = record.to_dict()
        out["signal_id"] = str(uuid.uuid4())
        out["tenant_id"] = tenant
        out["expires_at"] = now + 60
        run_query(self.conn, "signals.insert", tenant, {
            "signal_id": out["signal_id"], "idempotency_key": body["idempotency_key"],
            "decision": out["decision"], "record_json": json.dumps(out),
            "config_hash": out["config_hash"], "data_hash": out["data_hash"], "created_at": now})
        self._audit(tenant, "signal.evaluated", {"signal_id": out["signal_id"], "decision": out["decision"]}, now)
        return {"status": "ok", "signal": out}

    # ---- helpers -------------------------------------------------------
    def _require(self, tenant: str, feature: str, now: int) -> None:
        if not has_feature(self.conn, tenant, feature, now):
            raise ApiError(403, f"NOT_ENTITLED:{feature}")

    @staticmethod
    def _validate_body(body: dict, now: int) -> None:
        if not isinstance(body, dict):
            raise ApiError(400, "BODY_NOT_OBJECT")
        if "tenant_id" in body:
            raise ApiError(400, "TENANT_ID_NOT_ACCEPTED")
        extra, missing = set(body) - BODY_KEYS, BODY_KEYS - set(body)
        if extra or missing:
            raise ApiError(400, f"BAD_FIELDS:extra={sorted(extra)},missing={sorted(missing)}")
        if body["schema_version"] != SIGNAL_SCHEMA_VERSION:
            raise ApiError(400, "UNSUPPORTED_SCHEMA_VERSION")
        k = body["idempotency_key"]
        if not isinstance(k, str) or not (8 <= len(k) <= 128):
            raise ApiError(400, "BAD_IDEMPOTENCY_KEY")
        ts = body["request_ts"]
        if not isinstance(ts, int) or abs(now - ts) > REPLAY_WINDOW_SECONDS:
            raise ApiError(400, "REQUEST_TS_OUT_OF_WINDOW")
        if not isinstance(body["candles"], list) or not (1 <= len(body["candles"]) <= MAX_CANDLES):
            raise ApiError(413, "CANDLES_COUNT_OUT_OF_RANGE")
        acct = body["account"]
        if not isinstance(acct, dict) or set(acct) - {"open_positions", "daily_pnl_pct", "current_spread"}:
            raise ApiError(400, "BAD_ACCOUNT_FIELDS")

    @staticmethod
    def _series(body: dict) -> CandleSeries:
        p = body["provenance"]
        try:
            itype = InstrumentType(p["instrument_type"])
            prov = Provenance(str(p["symbol"]), itype, str(p["timeframe"]), str(p["source"]))
            candles = tuple(Candle(int(c["ts"]), float(c["open"]), float(c["high"]), float(c["low"]),
                                   float(c["close"]), float(c.get("volume", 0.0)),
                                   float(c["spread"]) if c.get("spread") is not None else None)
                            for c in body["candles"])
        except (KeyError, TypeError, ValueError):
            raise ApiError(400, "BAD_MARKET_DATA") from None
        return CandleSeries(prov, candles)

    def _audit(self, tenant: str, kind: str, payload: dict, now: int) -> None:
        run_query(self.conn, "audit.insert", tenant, {
            "event_id": str(uuid.uuid4()), "kind": kind,
            "payload_json": json.dumps(payload), "created_at": now})
