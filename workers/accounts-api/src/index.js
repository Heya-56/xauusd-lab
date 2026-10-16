// Hinova Trading Lab — accounts API (Cloudflare Worker + D1).
//
// Scope: sign-up, login, sessions, trial status, and MT5 terminal keys.
// Out of scope by design: strategy math, signals, prices, orders. Signals come
// only from the deterministic Python core; this Worker never computes them.
//
// Security: PBKDF2 password hashes, hashed session tokens and terminal keys,
// HttpOnly/Secure/SameSite=Strict cookie, Origin check on state-changing calls,
// login rate limit, parameterized SQL only, tenant derived from the session.

import commercial from "../../../config/commercial.json" with { type: "json" };

const DAY = 86400;
const SESSION_TTL = 7 * DAY;
const MAX_TERMINALS = 3;
const LOGIN_WINDOW = 15 * 60;
const LOGIN_MAX_ATTEMPTS = 5;
const COOKIE = "hl_session";

// ---------------------------------------------------------------- helpers
const enc = new TextEncoder();
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const fromB64url = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const randomToken = (bytes = 32) => b64url(crypto.getRandomValues(new Uint8Array(bytes)));
const sha256hex = async (s) => hex(await crypto.subtle.digest("SHA-256", enc.encode(s)));
const now = () => Math.floor(Date.now() / 1000);

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

export async function hashPassword(password, iterations, salt = crypto.getRandomValues(new Uint8Array(16))) {
  const key = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt, iterations }, key, 256);
  return `pbkdf2$${iterations}$${b64url(salt)}$${b64url(bits)}`;
}

export async function verifyPassword(password, stored) {
  const [scheme, iter, salt, expected] = String(stored).split("$");
  if (scheme !== "pbkdf2") return false;
  const recomputed = await hashPassword(password, Number(iter), fromB64url(salt));
  return timingSafeEqual(recomputed.split("$")[3], expected);
}

class HttpError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}

function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
               "X-Content-Type-Options": "nosniff", ...headers },
  });
}

async function readJson(request, allowed) {
  if (!(request.headers.get("Content-Type") || "").startsWith("application/json")) {
    throw new HttpError(415, "JSON_REQUIRED");
  }
  const text = await request.text();
  if (text.length > 4096) throw new HttpError(413, "BODY_TOO_LARGE");
  let body;
  try { body = JSON.parse(text); } catch { throw new HttpError(400, "INVALID_JSON"); }
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new HttpError(400, "BODY_NOT_OBJECT");
  const extra = Object.keys(body).filter((k) => !allowed.includes(k));
  if (extra.length) throw new HttpError(400, `UNKNOWN_FIELDS:${extra.join(",")}`);
  return body;
}

function cookieValue(request, name) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

const sessionCookie = (token, maxAge) =>
  `${COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${maxAge}`;

function checkOrigin(request, env) {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return;
  const origin = request.headers.get("Origin");
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (!origin || !allowed.includes(origin)) throw new HttpError(403, "ORIGIN_NOT_ALLOWED");
}

const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]{1,190}\.[a-z]{2,24}$/i;

// ---------------------------------------------------------------- auth
async function currentSession(request, env) {
  const token = cookieValue(request, COOKIE);
  if (!token) throw new HttpError(401, "UNAUTHENTICATED");
  const row = await env.DB.prepare(
    "SELECT user_id, tenant_id, expires_at FROM sessions WHERE token_hash = ?1"
  ).bind(await sha256hex(token)).first();
  if (!row || row.expires_at <= now()) throw new HttpError(401, "SESSION_EXPIRED");
  return row;
}

async function signup(request, env) {
  const { email, password } = await readJson(request, ["email", "password"]);
  const mail = String(email || "").trim().toLowerCase();
  if (!EMAIL_RE.test(mail)) throw new HttpError(422, "INVALID_EMAIL");
  if (typeof password !== "string" || password.length < 12 || password.length > 128) {
    throw new HttpError(422, "PASSWORD_12_TO_128_CHARS");
  }
  const exists = await env.DB.prepare("SELECT 1 AS x FROM users WHERE email = ?1").bind(mail).first();
  if (exists) throw new HttpError(409, "EMAIL_ALREADY_REGISTERED");
  const t = now();
  const tenantId = `tn_${randomToken(12)}`;
  const userId = `us_${randomToken(12)}`;
  const hash = await hashPassword(password, Number(env.PBKDF2_ITERATIONS || 100000));
  const trialEnds = t + commercial.trial_days * DAY;
  await env.DB.batch([
    env.DB.prepare("INSERT INTO tenants (tenant_id, display_name, created_at) VALUES (?1, ?2, ?3)")
      .bind(tenantId, mail, t),
    env.DB.prepare("INSERT INTO users (user_id, tenant_id, email, password_hash, created_at) VALUES (?1, ?2, ?3, ?4, ?5)")
      .bind(userId, tenantId, mail, hash, t),
    env.DB.prepare("INSERT INTO entitlements (tenant_id, plan, starts_at, ends_at, features) VALUES (?1, 'trial', ?2, ?3, ?4)")
      .bind(tenantId, t, trialEnds, JSON.stringify(commercial.plans.trial.features)),
  ]);
  return startSession(env, userId, tenantId, 201, { trial_ends_at: trialEnds });
}

async function startSession(env, userId, tenantId, status = 200, extra = {}) {
  const token = randomToken(32);
  const t = now();
  await env.DB.prepare(
    "INSERT INTO sessions (token_hash, user_id, tenant_id, created_at, expires_at) VALUES (?1, ?2, ?3, ?4, ?5)"
  ).bind(await sha256hex(token), userId, tenantId, t, t + SESSION_TTL).run();
  return json({ status: "ok", ...extra }, status, { "Set-Cookie": sessionCookie(token, SESSION_TTL) });
}

async function login(request, env) {
  const { email, password } = await readJson(request, ["email", "password"]);
  const mail = String(email || "").trim().toLowerCase();
  const t = now();
  const recent = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM login_attempts WHERE email = ?1 AND attempted_at > ?2"
  ).bind(mail, t - LOGIN_WINDOW).first();
  if (recent && recent.n >= LOGIN_MAX_ATTEMPTS) throw new HttpError(429, "TOO_MANY_ATTEMPTS");
  const user = await env.DB.prepare(
    "SELECT user_id, tenant_id, password_hash FROM users WHERE email = ?1"
  ).bind(mail).first();
  const ok = user && typeof password === "string" && (await verifyPassword(password, user.password_hash));
  if (!ok) {
    await env.DB.prepare("INSERT INTO login_attempts (email, attempted_at) VALUES (?1, ?2)").bind(mail, t).run();
    throw new HttpError(401, "INVALID_CREDENTIALS");   // same answer for unknown email and bad password
  }
  return startSession(env, user.user_id, user.tenant_id);
}

async function logout(request, env) {
  const token = cookieValue(request, COOKIE);
  if (token) await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?1").bind(await sha256hex(token)).run();
  return json({ status: "ok" }, 200, { "Set-Cookie": sessionCookie("", 0) });
}

async function me(request, env) {
  const s = await currentSession(request, env);
  const t = now();
  const user = await env.DB.prepare("SELECT email, created_at FROM users WHERE user_id = ?1").bind(s.user_id).first();
  const ents = await env.DB.prepare(
    "SELECT plan, starts_at, ends_at, features FROM entitlements WHERE tenant_id = ?1 ORDER BY ends_at DESC"
  ).bind(s.tenant_id).all();
  const active = (ents.results || []).filter((e) => e.starts_at <= t && e.ends_at > t);
  return json({
    email: user.email,
    plan: active[0]?.plan || "none",
    plan_ends_at: active[0]?.ends_at || null,
    features: [...new Set(active.flatMap((e) => JSON.parse(e.features)))],
    live_trading: "disabled",
  });
}

// ---------------------------------------------------------------- terminals
async function listTerminals(request, env) {
  const s = await currentSession(request, env);
  const rows = await env.DB.prepare(
    "SELECT terminal_id, label, key_prefix, created_at, last_seen_at FROM terminals " +
    "WHERE tenant_id = ?1 AND revoked_at IS NULL ORDER BY created_at"
  ).bind(s.tenant_id).all();
  return json({ terminals: rows.results || [], max: MAX_TERMINALS });
}

async function createTerminal(request, env) {
  const s = await currentSession(request, env);
  const { label } = await readJson(request, ["label"]);
  const name = String(label || "").trim();
  if (name.length < 1 || name.length > 40) throw new HttpError(422, "LABEL_1_TO_40_CHARS");
  const count = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM terminals WHERE tenant_id = ?1 AND revoked_at IS NULL"
  ).bind(s.tenant_id).first();
  if (count.n >= MAX_TERMINALS) throw new HttpError(409, "MAX_TERMINALS_REACHED");
  const key = `htl_${randomToken(32)}`;
  const id = `tm_${randomToken(10)}`;
  await env.DB.prepare(
    "INSERT INTO terminals (terminal_id, tenant_id, label, key_hash, key_prefix, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)"
  ).bind(id, s.tenant_id, name, await sha256hex(key), key.slice(0, 10), now()).run();
  // The raw key is returned exactly once. Only its hash is stored.
  return json({ terminal_id: id, label: name, api_key: key, shown_once: true }, 201);
}

async function revokeTerminal(request, env, terminalId) {
  const s = await currentSession(request, env);
  const res = await env.DB.prepare(
    "UPDATE terminals SET revoked_at = ?1 WHERE terminal_id = ?2 AND tenant_id = ?3 AND revoked_at IS NULL"
  ).bind(now(), terminalId, s.tenant_id).run();
  if (!res.meta || res.meta.changes === 0) throw new HttpError(404, "TERMINAL_NOT_FOUND");
  return json({ status: "revoked" });
}

// ---------------------------------------------------------------- router
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const corsOrigin = request.headers.get("Origin");
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim());
    const cors = corsOrigin && allowed.includes(corsOrigin)
      ? { "Access-Control-Allow-Origin": corsOrigin, "Access-Control-Allow-Credentials": "true", "Vary": "Origin" }
      : {};
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: { ...cors,
        "Access-Control-Allow-Methods": "GET,POST,DELETE", "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "600" } });
    }
    try {
      checkOrigin(request, env);
      const p = url.pathname, m = request.method;
      let res;
      if (m === "GET" && p === "/v1/health") res = json({ status: "ok", service: "accounts-api" });
      else if (m === "POST" && p === "/v1/auth/signup") res = await signup(request, env);
      else if (m === "POST" && p === "/v1/auth/login") res = await login(request, env);
      else if (m === "POST" && p === "/v1/auth/logout") res = await logout(request, env);
      else if (m === "GET" && p === "/v1/me") res = await me(request, env);
      else if (m === "GET" && p === "/v1/terminals") res = await listTerminals(request, env);
      else if (m === "POST" && p === "/v1/terminals") res = await createTerminal(request, env);
      else if (m === "DELETE" && p.startsWith("/v1/terminals/")) res = await revokeTerminal(request, env, p.split("/")[3]);
      else res = json({ error: "NOT_FOUND" }, 404);
      for (const [k, v] of Object.entries(cors)) res.headers.set(k, v);
      return res;
    } catch (err) {
      if (err instanceof HttpError) return json({ error: err.code }, err.status, cors);
      return json({ error: "INTERNAL_ERROR" }, 500, cors);   // never leak internals
    }
  },
};
