-- Accounts, sessions and linked MT5 terminals (SQLite / Cloudflare D1).
-- No raw passwords, session tokens or terminal keys are stored: only salted
-- PBKDF2 hashes (passwords) and SHA-256 hashes (tokens, keys).
-- Broker logins/passwords are NEVER stored: the EA authenticates with a
-- terminal key generated here, and the broker account stays with the user.

CREATE TABLE IF NOT EXISTS users (
  user_id        TEXT PRIMARY KEY,
  tenant_id      TEXT NOT NULL REFERENCES tenants(tenant_id),
  email          TEXT NOT NULL UNIQUE,
  password_hash  TEXT NOT NULL,
  created_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash     TEXT PRIMARY KEY,
  user_id        TEXT NOT NULL REFERENCES users(user_id),
  tenant_id      TEXT NOT NULL,
  created_at     INTEGER NOT NULL,
  expires_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS terminals (
  terminal_id    TEXT PRIMARY KEY,
  tenant_id      TEXT NOT NULL REFERENCES tenants(tenant_id),
  label          TEXT NOT NULL,
  key_hash       TEXT NOT NULL UNIQUE,        -- sha256 hex, same format as src/api/service.KeyStore
  key_prefix     TEXT NOT NULL,               -- first chars, to help the user recognise a key
  created_at     INTEGER NOT NULL,
  revoked_at     INTEGER,
  last_seen_at   INTEGER
);

CREATE TABLE IF NOT EXISTS login_attempts (
  email          TEXT NOT NULL,
  attempted_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_terminals_tenant ON terminals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(email, attempted_at);
