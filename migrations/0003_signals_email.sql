-- Email verification / password reset tokens, and terminal attribution of signals.
ALTER TABLE users ADD COLUMN email_verified_at INTEGER;
ALTER TABLE signal_runs ADD COLUMN terminal_id TEXT;

CREATE TABLE IF NOT EXISTS email_tokens (
  token_hash   TEXT PRIMARY KEY,           -- sha256 of the emailed token; raw token never stored
  user_id      TEXT NOT NULL REFERENCES users(user_id),
  purpose      TEXT NOT NULL CHECK (purpose IN ('verify','reset')),
  created_at   INTEGER NOT NULL,
  expires_at   INTEGER NOT NULL,
  used_at      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens(user_id, purpose, created_at);
