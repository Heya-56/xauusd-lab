// EA signal gateway, strategy configuration and dashboard snapshot.
// The Worker authenticates, authorises and stores. All strategy maths and config
// validation happen in the Python engine; this file never computes a signal.
import { HttpError, hmacHex, json, now, randomToken, readJson } from "./lib.js";
import { currentSession, requireFeature } from "./auth.js";
import { terminalFromKey } from "./terminals.js";

const REPLAY_WINDOW = 300;
const SIGNAL_TTL = 60;
const MAX_CANDLES = 2000;
const RATE_PER_MIN = 30;
const CHART_CANDLES = 160;
const EA_KEYS = ["schema_version", "idempotency_key", "request_ts", "provenance", "candles", "account"];

export async function engine(env, path, body) {
  if (!env.ENGINE_URL || !env.ENGINE_SECRET) throw new HttpError(503, "ENGINE_NOT_CONFIGURED");
  const raw = JSON.stringify(body);
  const ts = String(now());
  let res;
  try {
    res = await fetch(env.ENGINE_URL.replace(/\/$/, "") + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Hinova-Ts": ts,
                 "X-Hinova-Sig": await hmacHex(env.ENGINE_SECRET, `${ts}\n${raw}`) },
      body: raw,
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    throw new HttpError(503, "ENGINE_UNAVAILABLE");          // EA fails closed: no signal
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 422) throw new HttpError(422, data.error || "INVALID_CONFIG");
  if (!res.ok) throw new HttpError(502, "ENGINE_ERROR");
  return data;
}

async function latestConfig(env, tenantId) {
  const row = await env.DB.prepare(
    "SELECT config_hash, config_json, created_at FROM strategy_configs WHERE tenant_id = ?1 ORDER BY created_at DESC LIMIT 1"
  ).bind(tenantId).first();
  return row ? { hash: row.config_hash, created_at: row.created_at, ...JSON.parse(row.config_json) } : null;
}

// ---------------------------------------------------------------- EA
function validateEaBody(b) {
  const extra = Object.keys(b).filter((k) => !EA_KEYS.includes(k));
  const missing = EA_KEYS.filter((k) => !(k in b));
  if ("tenant_id" in b) throw new HttpError(400, "TENANT_ID_NOT_ACCEPTED");
  if (extra.length || missing.length) throw new HttpError(400, "BAD_FIELDS");
  if (b.schema_version !== "1.0") throw new HttpError(400, "UNSUPPORTED_SCHEMA_VERSION");
  if (typeof b.idempotency_key !== "string" || b.idempotency_key.length < 8 || b.idempotency_key.length > 128) {
    throw new HttpError(400, "BAD_IDEMPOTENCY_KEY");
  }
  if (!Number.isInteger(b.request_ts) || Math.abs(now() - b.request_ts) > REPLAY_WINDOW) {
    throw new HttpError(400, "REQUEST_TS_OUT_OF_WINDOW");
  }
  if (!Array.isArray(b.candles) || b.candles.length < 1 || b.candles.length > MAX_CANDLES) {
    throw new HttpError(413, "CANDLES_COUNT_OUT_OF_RANGE");
  }
  if (!b.account || typeof b.account !== "object") throw new HttpError(400, "BAD_ACCOUNT_FIELDS");
}

const eaView = (rec) => ({
  signal_id: rec.signal_id, decision: rec.decision, execution_allowed: false, expires_at: rec.expires_at,
  as_of_ts: rec.as_of_ts, data_status: rec.data_status, risk_status: rec.risk_status,
  veto_codes: rec.veto_codes, reason_codes: rec.reason_codes, config_hash: rec.config_hash,
});

export async function eaSignal(request, env) {
  const term = await terminalFromKey(request, env);
  if (!term.email_verified_at) throw new HttpError(403, "EMAIL_NOT_VERIFIED");
  await requireFeature(env, term.tenant_id, "signals.read");
  const b = await readJson(request, null, 400 * 1024);
  validateEaBody(b);
  const prior = await env.DB.prepare(
    "SELECT record_json FROM signal_runs WHERE tenant_id = ?1 AND idempotency_key = ?2"
  ).bind(term.tenant_id, b.idempotency_key).first();
  if (prior) return json({ status: "replayed", signal: eaView(JSON.parse(prior.record_json)) });
  const recent = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM signal_runs WHERE tenant_id = ?1 AND created_at > ?2"
  ).bind(term.tenant_id, now() - 60).first();
  if (recent.n >= RATE_PER_MIN) throw new HttpError(429, "RATE_LIMITED");
  const cfg = await latestConfig(env, term.tenant_id);
  if (!cfg) throw new HttpError(409, "NO_CONFIG");

  const rec = await engine(env, "/internal/v1/evaluate",
    { config: cfg.raw, provenance: b.provenance, candles: b.candles, account: b.account });
  const t = now();
  rec.signal_id = `sg_${randomToken(12)}`;
  rec.tenant_id = term.tenant_id;
  rec.terminal_id = term.terminal_id;
  rec.expires_at = t + SIGNAL_TTL;
  rec.execution_allowed = false;
  const stored = { ...rec, chart: b.candles.slice(-CHART_CANDLES).map((c) => ({ ts: c.ts, o: c.open, h: c.high, l: c.low, c: c.close })) };
  await env.DB.batch([
    env.DB.prepare(
      "INSERT INTO signal_runs (tenant_id, signal_id, idempotency_key, decision, record_json, config_hash, data_hash, created_at, terminal_id) " +
      "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)"
    ).bind(term.tenant_id, rec.signal_id, b.idempotency_key, rec.decision, JSON.stringify(stored),
           rec.config_hash, rec.data_hash, t, term.terminal_id),
    env.DB.prepare("UPDATE terminals SET last_seen_at = ?1 WHERE terminal_id = ?2").bind(t, term.terminal_id),
  ]);
  return json({ status: "ok", signal: eaView(rec) });
}

// ---------------------------------------------------------------- config
export async function getConfig(request, env) {
  const s = await currentSession(request, env);
  const cfg = await latestConfig(env, s.tenant_id);
  return json({ config: cfg ? cfg.raw : null, config_hash: cfg ? cfg.hash : null });
}

export async function putConfig(request, env) {
  const s = await currentSession(request, env);
  await requireFeature(env, s.tenant_id, "config.write");
  const raw = await readJson(request, ["profile", "strategies"], 16 * 1024);
  const v = await engine(env, "/internal/v1/config/validate", { config: raw });
  await env.DB.prepare(
    "INSERT OR REPLACE INTO strategy_configs (tenant_id, config_hash, config_json, created_at, created_by) VALUES (?1, ?2, ?3, ?4, ?5)"
  ).bind(s.tenant_id, v.config_hash, JSON.stringify({ raw, normalized: v.config }), now(), s.user_id).run();
  return json({ status: "stored", config_hash: v.config_hash });
}

// ---------------------------------------------------------------- dashboard
function placeholderSignal(profile) {
  return { schema_version: "1.0", decision: "NO_TRADE", data_status: "missing", risk_status: "blocked",
           execution_allowed: false, veto_codes: [], reason_codes: ["NO_SIGNAL_YET"], strategy_ids: [],
           strategy_results: [], config_hash: "—", data_hash: "—", profile, timeframe: "—", mode: "research",
           as_of_ts: 0, agent_review: null };
}

export async function dashboard(request, env) {
  const s = await currentSession(request, env);
  const [catalog, cfg, rows] = await Promise.all([
    engine(env, "/internal/v1/catalog", {}),
    latestConfig(env, s.tenant_id),
    env.DB.prepare("SELECT record_json FROM signal_runs WHERE tenant_id = ?1 ORDER BY created_at DESC LIMIT 12")
      .bind(s.tenant_id).all(),
  ]);
  const records = (rows.results || []).map((r) => JSON.parse(r.record_json));
  const raw = cfg ? cfg.raw : { profile: "intraday", strategies: {} };
  const enabled = Object.entries(raw.strategies || {}).filter(([, v]) => v && v.enabled === true).map(([k]) => k);
  const latest = records[0] || placeholderSignal(raw.profile);
  const chart = latest.chart || [];
  delete latest.chart;
  return json({
    snapshot_kind: "LIVE",
    disclaimer: records.length ? null : "Aucun signal reçu pour l'instant : connectez un terminal MT5 et lancez l'EA Hinova Bridge.",
    provenance: { symbol: "XAUUSD", instrument_type: latest.instrument_type || "—", timeframe: latest.timeframe || "—",
                  source: latest.source || "—", candles: chart.length, data_hash: latest.data_hash || "—",
                  quality: latest.data_status || "missing" },
    catalog: catalog.strategies, profiles: catalog.profiles,
    active_config: { profile: raw.profile, enabled, config_hash: cfg ? cfg.hash : null },
    candles: chart, latest_signal: latest,
    recent_signals: records.filter((r) => r.decision !== "NO_TRADE").map((r) => ({
      ts: r.as_of_ts, decision: r.decision, price: (r.chart || []).slice(-1)[0]?.c ?? null, reasons: (r.reason_codes || []).slice(-1) })),
    performance: {},
  });
}
