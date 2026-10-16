"""Allow-listed, parameterized, tenant-scoped SQL.

Callers (API services, agents) choose a QUERY ID and pass parameters. They can
never submit SQL text. Every template binds :tenant_id, which comes from the
authenticated principal — not from the request body. Adding a query means a
code change, a test and a review.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# query_id -> (sql, {param: type}, kind)
QUERIES: dict[str, tuple[str, dict[str, type], str]] = {
    "config.latest": (
        "SELECT config_hash, config_json, created_at FROM strategy_configs "
        "WHERE tenant_id = :tenant_id ORDER BY created_at DESC LIMIT 1", {}, "read"),
    "config.insert": (
        "INSERT OR IGNORE INTO strategy_configs (tenant_id, config_hash, config_json, created_at, created_by) "
        "VALUES (:tenant_id, :config_hash, :config_json, :created_at, :created_by)",
        {"config_hash": str, "config_json": str, "created_at": int, "created_by": str}, "write"),
    "signals.recent": (
        "SELECT signal_id, decision, record_json, created_at FROM signal_runs "
        "WHERE tenant_id = :tenant_id ORDER BY created_at DESC LIMIT :limit", {"limit": int}, "read"),
    "signals.by_idempotency": (
        "SELECT signal_id, record_json FROM signal_runs "
        "WHERE tenant_id = :tenant_id AND idempotency_key = :idempotency_key",
        {"idempotency_key": str}, "read"),
    "signals.insert": (
        "INSERT INTO signal_runs (tenant_id, signal_id, idempotency_key, decision, record_json, "
        "config_hash, data_hash, created_at) VALUES (:tenant_id, :signal_id, :idempotency_key, "
        ":decision, :record_json, :config_hash, :data_hash, :created_at)",
        {"signal_id": str, "idempotency_key": str, "decision": str, "record_json": str,
         "config_hash": str, "data_hash": str, "created_at": int}, "write"),
    "entitlements.active": (
        "SELECT plan, starts_at, ends_at, features FROM entitlements "
        "WHERE tenant_id = :tenant_id AND starts_at <= :now AND ends_at > :now", {"now": int}, "read"),
    "entitlements.insert": (
        "INSERT OR IGNORE INTO entitlements (tenant_id, plan, starts_at, ends_at, features) "
        "VALUES (:tenant_id, :plan, :starts_at, :ends_at, :features)",
        {"plan": str, "starts_at": int, "ends_at": int, "features": str}, "write"),
    "entitlements.any_trial": (
        "SELECT COUNT(*) AS n FROM entitlements WHERE tenant_id = :tenant_id AND plan = 'trial'", {}, "read"),
    "audit.insert": (
        "INSERT INTO audit_events (tenant_id, event_id, kind, payload_json, created_at) "
        "VALUES (:tenant_id, :event_id, :kind, :payload_json, :created_at)",
        {"event_id": str, "kind": str, "payload_json": str, "created_at": int}, "write"),
}

READ_ONLY_FOR_AGENTS = frozenset(k for k, v in QUERIES.items() if v[2] == "read")


class QueryError(ValueError):
    pass


def run_query(conn: sqlite3.Connection, query_id: str, tenant_id: str, params: dict | None = None,
              *, allowed: frozenset[str] | None = None) -> list[dict]:
    if query_id not in QUERIES:
        raise QueryError(f"query {query_id!r} is not allow-listed")
    if allowed is not None and query_id not in allowed:
        raise QueryError(f"query {query_id!r} not permitted for this caller")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise QueryError("tenant_id required")
    sql, spec, kind = QUERIES[query_id]
    params = dict(params or {})
    if "tenant_id" in params:
        raise QueryError("tenant_id cannot be supplied as a parameter")
    if set(params) != set(spec):
        raise QueryError(f"{query_id}: expected params {sorted(spec)}, got {sorted(params)}")
    for k, t in spec.items():
        if isinstance(params[k], bool) or not isinstance(params[k], t):
            raise QueryError(f"{query_id}: {k} must be {t.__name__}")
    params["tenant_id"] = tenant_id
    cur = conn.execute(sql, params)
    if kind == "write":
        conn.commit()
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    for mig in sorted(MIGRATIONS_DIR.glob("*.sql")):
        conn.executescript(mig.read_text(encoding="utf-8"))
    return conn
