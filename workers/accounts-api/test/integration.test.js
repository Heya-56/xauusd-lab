// Worker + REAL Python engine (spawned), D1 via node:sqlite. No fetch stubs for the engine.
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createServer } from "node:net";
import worker from "../src/index.js";
import { makeD1 } from "./d1-shim.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const SECRET = "i".repeat(48);
const ORIGIN = "https://app.example.test";
let proc, port;

const freePort = () => new Promise((res) => {
  const s = createServer().listen(0, () => { const p = s.address().port; s.close(() => res(p)); });
});

before(async () => {
  port = await freePort();
  proc = spawn("python3", ["-m", "src.api.engine_http"], { cwd: ROOT,
    env: { ...process.env, HINOVA_ENGINE_SECRET: SECRET, HINOVA_ENGINE_PORT: String(port) }, stdio: "ignore" });
  for (let i = 0; i < 80; i++) {
    try { if ((await fetch(`http://127.0.0.1:${port}/healthz`)).ok) return; } catch { /* starting */ }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("engine did not start");
});
after(() => proc && proc.kill());

const env = () => ({ DB: makeD1(join(ROOT, "migrations")), ALLOWED_ORIGINS: ORIGIN, PBKDF2_ITERATIONS: "1000",
  DEV_MODE: "true", APP_URL: ORIGIN, ENGINE_URL: `http://127.0.0.1:${port}`, ENGINE_SECRET: SECRET });

async function call(e, method, path, body, { cookie, auth, origin = ORIGIN } = {}) {
  const headers = {};
  if (origin) headers.Origin = origin;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (cookie) headers.Cookie = cookie;
  if (auth) headers.Authorization = auth;
  const res = await worker.fetch(new Request(`https://api.test${path}`, { method, headers,
    body: body === undefined ? undefined : JSON.stringify(body) }), e);
  const set = res.headers.get("Set-Cookie");
  return { status: res.status, body: await res.json(), cookie: set ? set.split(";")[0] : null };
}

function candles(n) {
  const step = 900, last = Math.floor(Date.now() / 1000 / step) * step - step;
  let p = 2410; const out = [];
  for (let i = 0; i < n; i++) {
    const o = p; p = +(p * (1 + 0.0006 * Math.sin(i / 20) + 0.0008 * Math.cos(i / 7))).toFixed(2);
    out.push({ ts: last - (n - 1 - i) * step, open: +o.toFixed(2), high: +(Math.max(o, p) + 0.4).toFixed(2),
               low: +(Math.min(o, p) - 0.4).toFixed(2), close: p, spread: 0.28 });
  }
  return out;
}

test("sign-up -> config -> EA candles -> real engine decision -> dashboard", async () => {
  const e = env();
  const s = await call(e, "POST", "/v1/auth/signup", { email: "it@example.com", password: "integration password" });
  assert.equal(s.status, 201);
  e.DB.raw.prepare("UPDATE users SET email_verified_at = 1").run();          // simulate the verification link
  const bad = await call(e, "PUT", "/v1/config",
    { profile: "intraday", strategies: { sata_mql5_parity: { enabled: true } } }, { cookie: s.cookie });
  assert.equal(bad.status, 422);                                              // validated by the real registry
  const cfg = await call(e, "PUT", "/v1/config",
    { profile: "intraday", strategies: { sr_breakout: { enabled: true } } }, { cookie: s.cookie });
  assert.equal(cfg.status, 200);
  const key = (await call(e, "POST", "/v1/terminals", { label: "MT5" }, { cookie: s.cookie })).body.api_key;
  const body = { schema_version: "1.0", idempotency_key: "it-0000001", request_ts: Math.floor(Date.now() / 1000),
    provenance: { symbol: "XAUUSD", instrument_type: "cfd", timeframe: "M15", source: "mt5:it" },
    candles: candles(300), account: { open_positions: 0, daily_pnl_pct: 0, current_spread: 0.28 } };
  const r = await call(e, "POST", "/v1/ea/signal", body, { auth: `Bearer ${key}`, origin: null });
  assert.equal(r.status, 200);
  assert.equal(r.body.signal.data_status, "valid");
  assert.ok(["BUY", "SELL", "NO_TRADE"].includes(r.body.signal.decision));
  assert.equal(r.body.signal.execution_allowed, false);
  assert.equal(r.body.signal.config_hash, cfg.body.config_hash);              // decision bound to the stored config
  const wrongTf = await call(e, "POST", "/v1/ea/signal", { ...body, idempotency_key: "it-0000002",
    provenance: { ...body.provenance, timeframe: "H4" } }, { auth: `Bearer ${key}`, origin: null });
  assert.equal(wrongTf.body.signal.decision, "NO_TRADE");                      // profile timeframe mismatch fails closed
  const d = await call(e, "GET", "/v1/dashboard", undefined, { cookie: s.cookie });
  assert.equal(d.body.snapshot_kind, "LIVE");
  assert.ok(d.body.catalog.some((x) => x.strategy_id === "sr_breakout"));
});

test("wrong engine secret is rejected by the real engine (fail closed)", async () => {
  const e = { ...env(), ENGINE_SECRET: "w".repeat(48) };
  const s = await call(e, "POST", "/v1/auth/signup", { email: "it2@example.com", password: "integration password" });
  const r = await call(e, "PUT", "/v1/config", { profile: "intraday", strategies: {} }, { cookie: s.cookie });
  assert.equal(r.status, 502);
});
