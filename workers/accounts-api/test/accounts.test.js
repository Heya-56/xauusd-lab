import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import worker, { hashPassword, verifyPassword } from "../src/index.js";
import { makeD1 } from "./d1-shim.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../..");
const ORIGIN = "https://app.example.test";
const env = () => ({ DB: makeD1(join(ROOT, "migrations")), ALLOWED_ORIGINS: ORIGIN, PBKDF2_ITERATIONS: "1000" });

async function call(e, method, path, body, cookie, origin = ORIGIN) {
  const headers = { Origin: origin };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (cookie) headers.Cookie = cookie;
  const res = await worker.fetch(new Request(`https://api.example.test${path}`,
    { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }), e);
  const set = res.headers.get("Set-Cookie");
  return { status: res.status, body: await res.json(), cookie: set ? set.split(";")[0] : null, headers: res.headers };
}

const signup = (e, email = "heya@example.com") => call(e, "POST", "/v1/auth/signup", { email, password: "correct horse battery" });

test("password hashing round-trip and wrong password", async () => {
  const h = await hashPassword("s3cret-password!", 1000);
  assert.ok(h.startsWith("pbkdf2$1000$"));
  assert.equal(await verifyPassword("s3cret-password!", h), true);
  assert.equal(await verifyPassword("wrong-password!!", h), false);
});

test("signup creates tenant, 7-day trial and a secure session cookie", async () => {
  const e = env();
  const r = await signup(e);
  assert.equal(r.status, 201);
  assert.match(r.headers.get("Set-Cookie"), /HttpOnly; Secure; SameSite=Strict/);
  const me = await call(e, "GET", "/v1/me", undefined, r.cookie);
  assert.equal(me.body.plan, "trial");
  assert.equal(me.body.live_trading, "disabled");
  assert.equal(r.body.trial_ends_at - Math.floor(Date.now() / 1000) > 6.9 * 86400, true);
  const raw = e.DB.raw.prepare("SELECT password_hash FROM users").get().password_hash;
  assert.ok(!raw.includes("correct horse"));
});

test("duplicate email, weak password, unknown fields rejected", async () => {
  const e = env();
  await signup(e);
  assert.equal((await signup(e)).status, 409);
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "a@b.co", password: "short" })).status, 422);
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "a@b.co", password: "x".repeat(20), role: "admin" })).status, 400);
});

test("login: same error for unknown email and bad password, then rate limited", async () => {
  const e = env();
  await signup(e);
  const a = await call(e, "POST", "/v1/auth/login", { email: "nobody@example.com", password: "whatever-password" });
  const b = await call(e, "POST", "/v1/auth/login", { email: "heya@example.com", password: "bad-password-123" });
  assert.deepEqual([a.status, a.body], [b.status, b.body]);
  for (let i = 0; i < 4; i++) await call(e, "POST", "/v1/auth/login", { email: "heya@example.com", password: "bad-password-123" });
  const locked = await call(e, "POST", "/v1/auth/login", { email: "heya@example.com", password: "correct horse battery" });
  assert.equal(locked.status, 429);
});

test("foreign origin and missing session are refused", async () => {
  const e = env();
  assert.equal((await call(e, "POST", "/v1/auth/signup", { email: "x@y.co", password: "x".repeat(20) }, null, "https://evil.test")).status, 403);
  assert.equal((await call(e, "GET", "/v1/me")).status, 401);
});

test("terminal keys: shown once, hashed, max 3, revocable, tenant-isolated", async () => {
  const e = env();
  const a = await signup(e, "a@example.com");
  const b = await signup(e, "b@example.com");
  const t = await call(e, "POST", "/v1/terminals", { label: "MT5 VPS" }, a.cookie);
  assert.equal(t.status, 201);
  assert.match(t.body.api_key, /^htl_/);
  const stored = e.DB.raw.prepare("SELECT key_hash FROM terminals").get().key_hash;
  assert.notEqual(stored, t.body.api_key);
  assert.equal(stored.length, 64);                                   // sha256 hex, as Python KeyStore
  const list = await call(e, "GET", "/v1/terminals", undefined, a.cookie);
  assert.equal(list.body.terminals.length, 1);
  assert.equal(JSON.stringify(list.body).includes(t.body.api_key), false);   // never shown again
  assert.equal((await call(e, "GET", "/v1/terminals", undefined, b.cookie)).body.terminals.length, 0);
  assert.equal((await call(e, "DELETE", `/v1/terminals/${t.body.terminal_id}`, undefined, b.cookie)).status, 404);
  assert.equal((await call(e, "DELETE", `/v1/terminals/${t.body.terminal_id}`, undefined, a.cookie)).status, 200);
  for (let i = 0; i < 3; i++) assert.equal((await call(e, "POST", "/v1/terminals", { label: `T${i}` }, a.cookie)).status, 201);
  assert.equal((await call(e, "POST", "/v1/terminals", { label: "T4" }, a.cookie)).status, 409);
});

test("logout invalidates the session", async () => {
  const e = env();
  const s = await signup(e);
  await call(e, "POST", "/v1/auth/logout", undefined, s.cookie);
  assert.equal((await call(e, "GET", "/v1/me", undefined, s.cookie)).status, 401);
});

test("terminal key hash matches Python KeyStore.hash_key (sha256 hex)", async () => {
  const { createHash } = await import("node:crypto");
  const e = env();
  const s = await signup(e);
  const t = await call(e, "POST", "/v1/terminals", { label: "x" }, s.cookie);
  const stored = e.DB.raw.prepare("SELECT key_hash FROM terminals").get().key_hash;
  assert.equal(stored, createHash("sha256").update(t.body.api_key).digest("hex"));
});
