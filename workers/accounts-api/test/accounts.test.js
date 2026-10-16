import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import worker, { hashPassword, verifyPassword } from "../src/index.js";
import { makeD1 } from "./d1-shim.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const ORIGIN = "https://app.example.test";
const SECRET = "e".repeat(40);

// ---- fake external services (Turnstile, Resend, Python engine) ------------------
let outbox, engineCalls, engineMode, realFetch;
beforeEach(() => {
  outbox = []; engineCalls = []; engineMode = "ok";
  realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    const u = String(url);
    if (u.startsWith("https://challenges.cloudflare.com/")) {
      const token = init.body.get("response");
      return Response.json({ success: token === "good-captcha" });
    }
    if (u === "https://api.resend.com/emails") {
      outbox.push(JSON.parse(init.body));
      return Response.json({ id: "em_1" });
    }
    if (u.startsWith("https://engine.test/")) {
      engineCalls.push({ path: new URL(u).pathname, headers: init.headers, body: JSON.parse(init.body) });
      if (engineMode === "down") throw new TypeError("fetch failed");
      const path = new URL(u).pathname;
      if (path === "/internal/v1/config/validate") {
        const cfg = JSON.parse(init.body).config;
        if (cfg.strategies && cfg.strategies.sata_mql5_parity?.enabled) return Response.json({ error: "INVALID_CONFIG:x" }, { status: 422 });
        return Response.json({ config: cfg, config_hash: "cfg_" + cfg.profile });
      }
      if (path === "/internal/v1/catalog") return Response.json({ strategies: [{ strategy_id: "macd_cross" }], profiles: { intraday: {} } });
      if (path === "/internal/v1/evaluate") {
        return Response.json({ schema_version: "1.0", decision: "BUY", data_status: "valid", risk_status: "allowed",
                               execution_allowed: true, veto_codes: [], reason_codes: ["LIVE_EXECUTION_DISABLED"],
                               config_hash: "cfg_intraday", data_hash: "d1", as_of_ts: 1, strategy_ids: ["macd_cross"],
                               strategy_results: [], timeframe: "M15", profile: "intraday", mode: "research" });
      }
    }
    throw new Error("unexpected fetch " + u);
  };
});
afterEach(() => { globalThis.fetch = realFetch; });

const env = (over = {}) => ({ DB: makeD1(join(ROOT, "migrations")), ALLOWED_ORIGINS: ORIGIN, PBKDF2_ITERATIONS: "1000",
  TURNSTILE_SECRET: "ts-secret", RESEND_API_KEY: "re_test", EMAIL_FROM: "Hinova <no-reply@example.test>",
  APP_URL: ORIGIN, ENGINE_URL: "https://engine.test", ENGINE_SECRET: SECRET, ...over });

async function call(e, method, path, body, { cookie, origin = ORIGIN, auth } = {}) {
  const headers = {};
  if (origin) headers.Origin = origin;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (cookie) headers.Cookie = cookie;
  if (auth) headers.Authorization = auth;
  const res = await worker.fetch(new Request(`https://api.example.test${path}`,
    { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }), e);
  const set = res.headers.get("Set-Cookie");
  return { status: res.status, body: await res.json(), cookie: set ? set.split(";")[0] : null, headers: res.headers };
}

const PW = "correct horse battery";
const signup = (e, email = "heya@example.com") => call(e, "POST", "/v1/auth/signup", { email, password: PW, turnstile_token: "good-captcha" });
const tokenFrom = (mail, param) => new URL(/https?:\/\/\S+/.exec(mail.text)[0]).searchParams.get(param);

async function verifiedUser(e, email) {
  const s = await signup(e, email);
  const tok = tokenFrom(outbox.findLast((m) => m.to[0] === email), "verify");
  assert.equal((await call(e, "POST", "/v1/auth/verify", { token: tok })).status, 200);
  return s.cookie;
}

// ---------------------------------------------------------------- accounts
test("password hashing round-trip and wrong password", async () => {
  const h = await hashPassword("s3cret-password!", 1000);
  assert.ok(h.startsWith("pbkdf2$1000$"));
  assert.equal(await verifyPassword("s3cret-password!", h), true);
  assert.equal(await verifyPassword("wrong-password!!", h), false);
});

test("signup: captcha required, 7-day trial, secure cookie, verification email, no plaintext", async () => {
  const e = env();
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "a@b.co", password: PW })).body.error, "CAPTCHA_REQUIRED");
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "a@b.co", password: PW, turnstile_token: "bad" })).status, 403);
  const r = await signup(e);
  assert.equal(r.status, 201);
  assert.match(r.headers.get("Set-Cookie"), /HttpOnly; Secure; SameSite=Strict/);
  assert.equal(r.body.email_verification, "sent");
  const me = await call(e, "GET", "/v1/me", undefined, { cookie: r.cookie });
  assert.deepEqual([me.body.plan, me.body.email_verified, me.body.live_trading], ["trial", false, "disabled"]);
  assert.ok(me.body.features.includes("config.write"));
  assert.ok(r.body.trial_ends_at - Math.floor(Date.now() / 1000) > 6.9 * 86400);
  const db = e.DB.raw;
  assert.ok(!db.prepare("SELECT password_hash FROM users").get().password_hash.includes("correct horse"));
  const tok = tokenFrom(outbox[0], "verify");
  assert.equal(db.prepare("SELECT COUNT(*) n FROM email_tokens WHERE token_hash = ?").get(tok).n, 0);   // only the hash is stored
});

test("captcha not configured fails closed outside dev mode", async () => {
  const e = env({ TURNSTILE_SECRET: "" });
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "a@b.co", password: PW })).body.error, "CAPTCHA_NOT_CONFIGURED");
  assert.equal((await call(env({ TURNSTILE_SECRET: "", DEV_MODE: "true" }), "POST", "/v1/auth/signup",
    { email: "a@b.co", password: PW })).status, 201);
});

test("duplicate email, weak password, unknown fields rejected", async () => {
  const e = env();
  await signup(e);
  assert.equal((await signup(e)).status, 409);
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "z@b.co", password: "short", turnstile_token: "good-captcha" })).status, 422);
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "z@b.co", password: PW, role: "admin" })).status, 400);
});

test("email verification: single use, required for terminals", async () => {
  const e = env();
  const s = await signup(e);
  assert.equal((await call(e, "POST", "/v1/terminals", { label: "x" }, { cookie: s.cookie })).body.error, "EMAIL_NOT_VERIFIED");
  const tok = tokenFrom(outbox[0], "verify");
  assert.equal((await call(e, "POST", "/v1/auth/verify", { token: tok })).status, 200);
  assert.equal((await call(e, "POST", "/v1/auth/verify", { token: tok })).status, 400);     // replay refused
  assert.equal((await call(e, "GET", "/v1/me", undefined, { cookie: s.cookie })).body.email_verified, true);
  assert.equal((await call(e, "POST", "/v1/terminals", { label: "x" }, { cookie: s.cookie })).status, 201);
});

test("login: same error for unknown email and bad password, then rate limited", async () => {
  const e = env();
  await signup(e);
  const a = await call(e, "POST", "/v1/auth/login", { email: "nobody@example.com", password: "whatever-password" });
  const b = await call(e, "POST", "/v1/auth/login", { email: "heya@example.com", password: "bad-password-123" });
  assert.deepEqual([a.status, a.body], [b.status, b.body]);
  for (let i = 0; i < 4; i++) await call(e, "POST", "/v1/auth/login", { email: "heya@example.com", password: "bad-password-123" });
  assert.equal((await call(e, "POST", "/v1/auth/login", { email: "heya@example.com", password: PW })).status, 429);
});

test("password reset: no enumeration, single use, sessions revoked, new password works", async () => {
  const e = env();
  const s = await signup(e);
  const before = outbox.length;
  const unknown = await call(e, "POST", "/v1/auth/password/forgot", { email: "nobody@example.com", turnstile_token: "good-captcha" });
  const known = await call(e, "POST", "/v1/auth/password/forgot", { email: "heya@example.com", turnstile_token: "good-captcha" });
  assert.deepEqual([unknown.status, unknown.body], [known.status, known.body]);
  assert.equal(outbox.length, before + 1);                                  // only the real account gets mail
  const tok = tokenFrom(outbox.at(-1), "reset");
  assert.equal((await call(e, "POST", "/v1/auth/password/reset", { token: tok, password: "short" })).status, 422);
  assert.equal((await call(e, "POST", "/v1/auth/password/reset", { token: tok, password: "a brand new passphrase" })).status, 200);
  assert.equal((await call(e, "POST", "/v1/auth/password/reset", { token: tok, password: "another new passphrase" })).status, 400);
  assert.equal((await call(e, "GET", "/v1/me", undefined, { cookie: s.cookie })).status, 401);   // old session killed
  assert.equal((await call(e, "POST", "/v1/auth/login", { email: "heya@example.com", password: PW })).status, 401);
  assert.equal((await call(e, "POST", "/v1/auth/login", { email: "heya@example.com", password: "a brand new passphrase" })).status, 200);
});

test("foreign origin and missing session are refused; logout invalidates", async () => {
  const e = env();
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "x@y.co", password: PW, turnstile_token: "good-captcha" },
    { origin: "https://evil.test" })).status, 403);
  assert.equal((await call(e, "GET", "/v1/me")).status, 401);
  const s = await signup(e);
  await call(e, "POST", "/v1/auth/logout", undefined, { cookie: s.cookie });
  assert.equal((await call(e, "GET", "/v1/me", undefined, { cookie: s.cookie })).status, 401);
});

// ---------------------------------------------------------------- terminals
test("terminal keys: shown once, sha256 like Python KeyStore, max 3, revocable, tenant-isolated", async () => {
  const e = env();
  const a = await verifiedUser(e, "a@example.com");
  const b = await verifiedUser(e, "b@example.com");
  const t = await call(e, "POST", "/v1/terminals", { label: "MT5 VPS" }, { cookie: a });
  assert.match(t.body.api_key, /^htl_/);
  const stored = e.DB.raw.prepare("SELECT key_hash FROM terminals").get().key_hash;
  assert.equal(stored, createHash("sha256").update(t.body.api_key).digest("hex"));
  const list = await call(e, "GET", "/v1/terminals", undefined, { cookie: a });
  assert.equal(JSON.stringify(list.body).includes(t.body.api_key), false);
  assert.equal((await call(e, "GET", "/v1/terminals", undefined, { cookie: b })).body.terminals.length, 0);
  assert.equal((await call(e, "DELETE", `/v1/terminals/${t.body.terminal_id}`, undefined, { cookie: b })).status, 404);
  assert.equal((await call(e, "DELETE", `/v1/terminals/${t.body.terminal_id}`, undefined, { cookie: a })).status, 200);
  for (let i = 0; i < 3; i++) assert.equal((await call(e, "POST", "/v1/terminals", { label: `T${i}` }, { cookie: a })).status, 201);
  assert.equal((await call(e, "POST", "/v1/terminals", { label: "T4" }, { cookie: a })).status, 409);
});

// ---------------------------------------------------------------- config + EA gateway
const EA_FIXTURE = JSON.parse(readFileSync(join(ROOT, "mql5/HinovaBridge/payload.example.json"), "utf8"));
const eaBody = (over = {}) => ({ ...EA_FIXTURE, request_ts: Math.floor(Date.now() / 1000), ...over });

async function readyTenant(e, email = "ea@example.com") {
  const cookie = await verifiedUser(e, email);
  assert.equal((await call(e, "PUT", "/v1/config", { profile: "intraday", strategies: { macd_cross: { enabled: true } } },
    { cookie })).status, 200);
  const key = (await call(e, "POST", "/v1/terminals", { label: "MT5" }, { cookie })).body.api_key;
  return { cookie, auth: `Bearer ${key}` };
}

test("config: validated by the engine, stored per tenant, invalid refused", async () => {
  const e = env();
  const cookie = await verifiedUser(e, "c@example.com");
  assert.equal((await call(e, "PUT", "/v1/config", { profile: "intraday", strategies: { sata_mql5_parity: { enabled: true } } },
    { cookie })).status, 422);
  assert.equal((await call(e, "PUT", "/v1/config", { profile: "intraday", strategies: {}, risk: 9 }, { cookie })).status, 400);
  const ok = await call(e, "PUT", "/v1/config", { profile: "swing", strategies: {} }, { cookie });
  assert.equal(ok.body.config_hash, "cfg_swing");
  assert.equal((await call(e, "GET", "/v1/config", undefined, { cookie })).body.config.profile, "swing");
  const other = await verifiedUser(e, "d@example.com");
  assert.equal((await call(e, "GET", "/v1/config", undefined, { cookie: other })).body.config, null);
});

test("EA signal: signed engine call, never executable, idempotent, stored, terminal seen", async () => {
  const e = env();
  const { auth } = await readyTenant(e);
  const r = await call(e, "POST", "/v1/ea/signal", eaBody(), { auth, origin: null });
  assert.equal(r.status, 200);
  assert.equal(r.body.signal.decision, "BUY");
  assert.equal(r.body.signal.execution_allowed, false);                       // even if the engine said true
  const call0 = engineCalls.find((c) => c.path === "/internal/v1/evaluate");
  assert.deepEqual(Object.keys(call0.body).sort(), ["account", "candles", "config", "provenance"]);   // no tenant id sent
  const { createHmac } = await import("node:crypto");
  const expected = createHmac("sha256", SECRET).update(`${call0.headers["X-Hinova-Ts"]}\n${JSON.stringify(call0.body)}`).digest("hex");
  assert.equal(call0.headers["X-Hinova-Sig"], expected);
  const again = await call(e, "POST", "/v1/ea/signal", eaBody(), { auth, origin: null });
  assert.equal(again.body.status, "replayed");
  assert.equal(again.body.signal.signal_id, r.body.signal.signal_id);
  assert.equal(e.DB.raw.prepare("SELECT COUNT(*) n FROM signal_runs").get().n, 1);
  assert.ok(e.DB.raw.prepare("SELECT last_seen_at FROM terminals").get().last_seen_at > 0);
});

test("EA signal refusals: bad key, revoked, spoofed tenant, stale request, no config, engine down", async () => {
  const e = env();
  const { cookie, auth } = await readyTenant(e);
  assert.equal((await call(e, "POST", "/v1/ea/signal", eaBody(), { auth: "Bearer htl_" + "x".repeat(43), origin: null })).status, 401);
  assert.equal((await call(e, "POST", "/v1/ea/signal", eaBody({ tenant_id: "tn_other" }), { auth, origin: null })).body.error, "TENANT_ID_NOT_ACCEPTED");
  assert.equal((await call(e, "POST", "/v1/ea/signal", eaBody({ request_ts: 1000 }), { auth, origin: null })).body.error, "REQUEST_TS_OUT_OF_WINDOW");
  assert.equal((await call(e, "POST", "/v1/ea/signal", eaBody({ schema_version: "9" }), { auth, origin: null })).status, 400);
  engineMode = "down";
  assert.equal((await call(e, "POST", "/v1/ea/signal", eaBody({ idempotency_key: "k-down-0001" }), { auth, origin: null })).body.error, "ENGINE_UNAVAILABLE");
  engineMode = "ok";
  const noCfg = await verifiedUser(e, "nocfg@example.com");
  const k2 = (await call(e, "POST", "/v1/terminals", { label: "x" }, { cookie: noCfg })).body.api_key;
  assert.equal((await call(e, "POST", "/v1/ea/signal", eaBody(), { auth: `Bearer ${k2}`, origin: null })).body.error, "NO_CONFIG");
  const tid = (await call(e, "GET", "/v1/terminals", undefined, { cookie })).body.terminals[0].terminal_id;
  await call(e, "DELETE", `/v1/terminals/${tid}`, undefined, { cookie });
  assert.equal((await call(e, "POST", "/v1/ea/signal", eaBody({ idempotency_key: "k-revoked-01" }), { auth, origin: null })).status, 401);
});

test("EA signal blocked when the trial has expired", async () => {
  const e = env();
  const { auth } = await readyTenant(e);
  e.DB.raw.prepare("UPDATE entitlements SET ends_at = 1").run();
  assert.equal((await call(e, "POST", "/v1/ea/signal", eaBody(), { auth, origin: null })).body.error, "NOT_ENTITLED:signals.read");
});

test("dashboard snapshot: live shape, tenant-isolated, chart from last EA payload", async () => {
  const e = env();
  const { cookie, auth } = await readyTenant(e);
  const empty = await call(e, "GET", "/v1/dashboard", undefined, { cookie });
  assert.equal(empty.body.latest_signal.reason_codes[0], "NO_SIGNAL_YET");
  await call(e, "POST", "/v1/ea/signal", eaBody(), { auth, origin: null });
  const d = await call(e, "GET", "/v1/dashboard", undefined, { cookie });
  assert.equal(d.body.snapshot_kind, "LIVE");
  assert.equal(d.body.latest_signal.decision, "BUY");
  assert.equal(d.body.candles.length, EA_FIXTURE.candles.length);
  assert.deepEqual(d.body.active_config.enabled, ["macd_cross"]);
  const other = await verifiedUser(e, "z@example.com");
  assert.equal((await call(e, "GET", "/v1/dashboard", undefined, { cookie: other })).body.latest_signal.reason_codes[0], "NO_SIGNAL_YET");
});
