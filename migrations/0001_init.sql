-- Hinova Trading Lab — schema v1 (SQLite / Cloudflare D1 compatible).
-- Every tenant-owned table carries tenant_id; access goes through
-- src/data/queries.py allow-listed templates which always bind tenant_id.
-- No secrets are stored here (no broker passwords, no API tokens).

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id     TEXT PRIMARY KEY,
  display_name  TEXT NOT NULL,
  created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS entitlements (
  tenant_id     TEXT NOT NULL REFERENCES tenants(tenant_id),
  plan          TEXT NOT NULL,              -- e.g. trial, subscription, white_label
  starts_at     INTEGER NOT NULL,
  ends_at       INTEGER NOT NULL,           -- server clock only
  features      TEXT NOT NULL,              -- JSON array of feature keys
  PRIMARY KEY (tenant_id, plan, starts_at)
);

CREATE TABLE IF NOT EXISTS strategy_configs (
  tenant_id     TEXT NOT NULL REFERENCES tenants(tenant_id),
  config_hash   TEXT NOT NULL,
  config_json   TEXT NOT NULL,              -- validated snapshot only
  created_at    INTEGER NOT NULL,
  created_by    TEXT NOT NULL,
  PRIMARY KEY (tenant_id, config_hash)
);

CREATE TABLE IF NOT EXISTS signal_runs (
  tenant_id     TEXT NOT NULL REFERENCES tenants(tenant_id),
  signal_id     TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  decision      TEXT NOT NULL CHECK (decision IN ('BUY','SELL','NO_TRADE')),
  record_json   TEXT NOT NULL,
  config_hash   TEXT NOT NULL,
  data_hash     TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, signal_id),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS audit_events (
  tenant_id     TEXT NOT NULL,
  event_id      TEXT NOT NULL,
  kind          TEXT NOT NULL,
  payload_json  TEXT NOT NULL,              -- redacted, no credentials
  created_at    INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_signal_runs_tenant_time ON signal_runs(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_tenant_time ON audit_events(tenant_id, created_at);
