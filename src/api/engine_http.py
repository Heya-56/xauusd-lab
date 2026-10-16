"""Signal engine HTTP service (stdlib only).

Runs the deterministic Python core behind the Cloudflare accounts Worker.
It is NOT exposed to browsers or terminals: every request must be signed by the
Worker with a shared secret (HMAC-SHA256 over timestamp + body). The Worker has
already authenticated the terminal/user and derived the tenant; this service is
stateless and never stores anything.

Routes (all POST except health):
  GET  /healthz
  POST /internal/v1/catalog          -> strategy catalog + profiles
  POST /internal/v1/config/validate  -> {"config": {...}} -> normalised config + hash
  POST /internal/v1/evaluate         -> {"config", "provenance", "candles", "account"} -> SignalRecord

Environment:
  HINOVA_ENGINE_SECRET   shared secret (required, >= 32 chars)
  HINOVA_ENGINE_PORT     default 8090
Run:  python -m src.api.engine_http
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.core.contracts import SIGNAL_SCHEMA_VERSION, InstrumentType
from src.core.engine import evaluate
from src.core.registry import ConfigError, StrategyRegistry, load_profiles, validate_config
from src.core.risk_gate import AccountState
from src.data.ohlc import Candle, CandleSeries, Provenance

MAX_BODY = 512 * 1024
MAX_CANDLES = 2000
SIG_WINDOW_S = 60
REGISTRY = StrategyRegistry()
PROFILES = load_profiles()


class EngineError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


def sign(secret: str, ts: str, body: bytes) -> str:
    return hmac.new(secret.encode(), ts.encode() + b"\n" + body, hashlib.sha256).hexdigest()


def verify(secret: str, ts: str | None, sig: str | None, body: bytes, now: float | None = None) -> None:
    if not secret or len(secret) < 32:
        raise EngineError(500, "ENGINE_SECRET_NOT_CONFIGURED")
    if not ts or not sig:
        raise EngineError(401, "MISSING_SIGNATURE")
    try:
        t = int(ts)
    except ValueError:
        raise EngineError(401, "BAD_TIMESTAMP") from None
    if abs((now or time.time()) - t) > SIG_WINDOW_S:
        raise EngineError(401, "SIGNATURE_EXPIRED")
    if not hmac.compare_digest(sign(secret, ts, body), sig):
        raise EngineError(401, "BAD_SIGNATURE")


def _series(body: dict) -> CandleSeries:
    p, candles = body.get("provenance"), body.get("candles")
    if not isinstance(p, dict) or not isinstance(candles, list) or not (1 <= len(candles) <= MAX_CANDLES):
        raise EngineError(400, "BAD_MARKET_DATA")
    try:
        prov = Provenance(str(p["symbol"]), InstrumentType(p["instrument_type"]), str(p["timeframe"]), str(p["source"]))
        cs = tuple(Candle(int(c["ts"]), float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"]),
                          float(c.get("volume", 0.0)),
                          float(c["spread"]) if c.get("spread") is not None else None) for c in candles)
    except (KeyError, TypeError, ValueError):
        raise EngineError(400, "BAD_MARKET_DATA") from None
    return CandleSeries(prov, cs)


def handle(path: str, body: dict, *, now: float | None = None) -> dict:
    """Pure request handler (testable without sockets)."""
    if path == "/internal/v1/catalog":
        return {"strategies": REGISTRY.catalog(), "profiles": PROFILES, "schema_version": SIGNAL_SCHEMA_VERSION}
    if path == "/internal/v1/config/validate":
        try:
            cfg = validate_config(body.get("config"), REGISTRY, PROFILES)
        except ConfigError as exc:
            raise EngineError(422, f"INVALID_CONFIG:{exc}") from None
        return {"config": cfg.to_dict(), "config_hash": cfg.config_hash}
    if path == "/internal/v1/evaluate":
        if set(body) - {"config", "provenance", "candles", "account"}:
            raise EngineError(400, "UNKNOWN_FIELDS")
        try:
            cfg = validate_config(body.get("config"), REGISTRY, PROFILES)
        except ConfigError as exc:
            raise EngineError(422, f"INVALID_CONFIG:{exc}") from None
        a = body.get("account") or {}
        if not isinstance(a, dict) or set(a) - {"open_positions", "daily_pnl_pct", "current_spread"}:
            raise EngineError(400, "BAD_ACCOUNT_FIELDS")
        try:
            acct = AccountState(int(a.get("open_positions", 0)), float(a.get("daily_pnl_pct", 0.0)),
                                float(a["current_spread"]) if a.get("current_spread") is not None else None)
        except (TypeError, ValueError):
            raise EngineError(400, "BAD_ACCOUNT_FIELDS") from None
        rec = evaluate(_series(body), cfg, REGISTRY, account=acct,
                       now_ts=int(now if now is not None else time.time()))
        out = rec.to_dict()
        out["execution_allowed"] = False          # belt and braces: never true from this service
        return out
    raise EngineError(404, "NOT_FOUND")


class _Handler(BaseHTTPRequestHandler):
    server_version = "HinovaEngine/1"

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path == "/healthz":
            return self._send(200, {"status": "ok"})
        return self._send(404, {"error": "NOT_FOUND"})

    def do_POST(self):  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                raise EngineError(413, "BODY_SIZE")
            raw = self.rfile.read(n)
            verify(os.environ.get("HINOVA_ENGINE_SECRET", ""), self.headers.get("X-Hinova-Ts"),
                   self.headers.get("X-Hinova-Sig"), raw)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                raise EngineError(400, "INVALID_JSON") from None
            if not isinstance(body, dict):
                raise EngineError(400, "BODY_NOT_OBJECT")
            self._send(200, handle(self.path, body))
        except EngineError as exc:
            self._send(exc.status, {"error": exc.code})
        except Exception:  # never leak internals
            self._send(500, {"error": "INTERNAL_ERROR"})

    def log_message(self, fmt, *args):  # no request bodies in logs
        print(f"[engine] {self.address_string()} {fmt % args}")


def main() -> None:
    if len(os.environ.get("HINOVA_ENGINE_SECRET", "")) < 32:
        raise SystemExit("HINOVA_ENGINE_SECRET must be set (>= 32 chars)")
    port = int(os.environ.get("HINOVA_ENGINE_PORT", "8090"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    print(f"[engine] listening on :{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
