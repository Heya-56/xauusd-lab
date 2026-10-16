"""Trial and subscription entitlements, evaluated with the SERVER clock.

Billing integration is intentionally absent: no payment provider is selected.
A future provider webhook must verify signatures and call `grant_plan`
idempotently. Expiry only blocks new premium API operations; it never sends,
closes or modifies trades.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.data.queries import run_query

POLICY = json.loads((Path(__file__).resolve().parents[2] / "config" / "commercial.json").read_text())
DAY = 86400


def start_trial(conn: sqlite3.Connection, tenant_id: str, now: int) -> bool:
    """Create the 7-day trial once per tenant. Returns False if already used."""
    if run_query(conn, "entitlements.any_trial", tenant_id)[0]["n"]:
        return False
    grant_plan(conn, tenant_id, "trial", now, now + POLICY["trial_days"] * DAY)
    return True


def grant_plan(conn: sqlite3.Connection, tenant_id: str, plan: str, starts_at: int, ends_at: int) -> None:
    if plan not in POLICY["plans"]:
        raise ValueError(f"unknown plan {plan!r}")
    if ends_at <= starts_at:
        raise ValueError("ends_at must be after starts_at")
    run_query(conn, "entitlements.insert", tenant_id, {
        "plan": plan, "starts_at": starts_at, "ends_at": ends_at,
        "features": json.dumps(POLICY["plans"][plan]["features"])})


def has_feature(conn: sqlite3.Connection, tenant_id: str, feature: str, now: int) -> bool:
    rows = run_query(conn, "entitlements.active", tenant_id, {"now": now})
    return any(feature in json.loads(r["features"]) for r in rows)
