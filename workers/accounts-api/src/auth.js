// Accounts: sign-up, login, sessions, email verification, password reset, Turnstile.
import commercial from "../../../config/commercial.json" with { type: "json" };
import { DAY, HttpError, b64url, cookieValue, enc, fromB64url, isDev, json, now, randomToken,
         readJson, sha256hex, timingSafeEqual } from "./lib.js";
import { sendEmail } from "./email.js";

export const COOKIE = "hl_session";
const SESSION_TTL = 7 * DAY;
const LOGIN_WINDOW = 15 * 60;
const LOGIN_MAX_ATTEMPTS = 5;
const VERIFY_TTL = DAY;
const RESET_TTL = 30 * 60;
const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]{1,190}\.[a-z]{2,24}$/i;

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

const sessionCookie = (token, maxAge) =>
  `${COOKIE}=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${maxAge}`;

function checkPassword(pw) {
  if (typeof pw !== "string" || pw.length < 12 || pw.length > 128) throw new HttpError(422, "PASSWORD_12_TO_128_CHARS");
}

export async function verifyTurnstile(env, token, request) {
  if (!env.TURNSTILE_SECRET) {
    if (isDev(env)) return;                                   // local development only
    throw new HttpError(503, "CAPTCHA_NOT_CONFIGURED");       // fail closed in every other environment
  }
  if (typeof token !== "string" || !token || token.length > 2048) throw new HttpError(400, "CAPTCHA_REQUIRED");
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", token);
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) form.append("remoteip", ip);
  let ok = false;
  try {
    const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
    ok = r.ok && (await r.json()).success === true;
  } catch { ok = false; }
  if (!ok) throw new HttpError(403, "CAPTCHA_FAILED");
}

export async function currentSession(request, env) {
  const token = cookieValue(request, COOKIE);
  if (!token) throw new HttpError(401, "UNAUTHENTICATED");
  const row = await env.DB.prepare(
    "SELECT s.user_id, s.tenant_id, s.expires_at, u.email, u.email_verified_at FROM sessions s " +
    "JOIN users u ON u.user_id = s.user_id WHERE s.token_hash = ?1"
  ).bind(await sha256hex(token)).first();
  if (!row || row.expires_at <= now()) throw new HttpError(401, "SESSION_EXPIRED");
  return row;
}

export async function requireFeature(env, tenantId, feature) {
  const t = now();
  const rows = await env.DB.prepare(
    "SELECT features FROM entitlements WHERE tenant_id = ?1 AND starts_at <= ?2 AND ends_at > ?2"
  ).bind(tenantId, t).all();
  const ok = (rows.results || []).some((r) => JSON.parse(r.features).includes(feature));
  if (!ok) throw new HttpError(403, `NOT_ENTITLED:${feature}`);
}

async function issueEmailToken(env, userId, purpose, ttl) {
  const token = randomToken(32);
  const t = now();
  await env.DB.prepare("UPDATE email_tokens SET used_at = ?1 WHERE user_id = ?2 AND purpose = ?3 AND used_at IS NULL")
    .bind(t, userId, purpose).run();                         // only the latest link stays valid
  await env.DB.prepare(
    "INSERT INTO email_tokens (token_hash, user_id, purpose, created_at, expires_at) VALUES (?1, ?2, ?3, ?4, ?5)"
  ).bind(await sha256hex(token), userId, purpose, t, t + ttl).run();
  return token;
}

async function consumeEmailToken(env, token, purpose) {
  if (typeof token !== "string" || token.length < 20 || token.length > 100) throw new HttpError(400, "INVALID_TOKEN");
  const h = await sha256hex(token);
  const row = await env.DB.prepare(
    "SELECT user_id, expires_at, used_at FROM email_tokens WHERE token_hash = ?1 AND purpose = ?2"
  ).bind(h, purpose).first();
  if (!row || row.used_at || row.expires_at <= now()) throw new HttpError(400, "INVALID_OR_EXPIRED_TOKEN");
  const res = await env.DB.prepare("UPDATE email_tokens SET used_at = ?1 WHERE token_hash = ?2 AND used_at IS NULL")
    .bind(now(), h).run();
  if (!res.meta || res.meta.changes !== 1) throw new HttpError(400, "INVALID_OR_EXPIRED_TOKEN");   // single use
  return row.user_id;
}

const link = (env, param, token) => `${(env.APP_URL || "").replace(/\/$/, "")}/account.html?${param}=${token}`;

async function sendVerification(env, userId, email) {
  const token = await issueEmailToken(env, userId, "verify", VERIFY_TTL);
  await sendEmail(env, email, "Confirmez votre adresse e-mail · Hinova Trading Lab",
    `Bienvenue sur Hinova Trading Lab.\n\nConfirmez votre adresse en ouvrant ce lien (valable 24 h) :\n${link(env, "verify", token)}\n\n` +
    "Si vous n'êtes pas à l'origine de cette inscription, ignorez ce message.");
}

async function startSession(env, userId, tenantId, status = 200, extra = {}) {
  const token = randomToken(32);
  const t = now();
  await env.DB.prepare(
    "INSERT INTO sessions (token_hash, user_id, tenant_id, created_at, expires_at) VALUES (?1, ?2, ?3, ?4, ?5)"
  ).bind(await sha256hex(token), userId, tenantId, t, t + SESSION_TTL).run();
  return json({ status: "ok", ...extra }, status, { "Set-Cookie": sessionCookie(token, SESSION_TTL) });
}

export async function signup(request, env) {
  const { email, password, turnstile_token } = await readJson(request, ["email", "password", "turnstile_token"]);
  await verifyTurnstile(env, turnstile_token, request);
  const mail = String(email || "").trim().toLowerCase();
  if (!EMAIL_RE.test(mail)) throw new HttpError(422, "INVALID_EMAIL");
  checkPassword(password);
  const exists = await env.DB.prepare("SELECT 1 AS x FROM users WHERE email = ?1").bind(mail).first();
  if (exists) throw new HttpError(409, "EMAIL_ALREADY_REGISTERED");
  const t = now();
  const tenantId = `tn_${randomToken(12)}`;
  const userId = `us_${randomToken(12)}`;
  const hash = await hashPassword(password, Number(env.PBKDF2_ITERATIONS || 100000));
  const trialEnds = t + commercial.trial_days * DAY;
  await env.DB.batch([
    env.DB.prepare("INSERT INTO tenants (tenant_id, display_name, created_at) VALUES (?1, ?2, ?3)").bind(tenantId, mail, t),
    env.DB.prepare("INSERT INTO users (user_id, tenant_id, email, password_hash, created_at) VALUES (?1, ?2, ?3, ?4, ?5)")
      .bind(userId, tenantId, mail, hash, t),
    env.DB.prepare("INSERT INTO entitlements (tenant_id, plan, starts_at, ends_at, features) VALUES (?1, 'trial', ?2, ?3, ?4)")
      .bind(tenantId, t, trialEnds, JSON.stringify(commercial.plans.trial.features)),
  ]);
  let verification = "sent";
  try { await sendVerification(env, userId, mail); } catch { verification = "failed"; }   // account kept; user can resend
  return startSession(env, userId, tenantId, 201, { trial_ends_at: trialEnds, email_verification: verification });
}

export async function login(request, env) {
  const { email, password } = await readJson(request, ["email", "password"]);
  const mail = String(email || "").trim().toLowerCase();
  const t = now();
  const recent = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM login_attempts WHERE email = ?1 AND attempted_at > ?2"
  ).bind(mail, t - LOGIN_WINDOW).first();
  if (recent && recent.n >= LOGIN_MAX_ATTEMPTS) throw new HttpError(429, "TOO_MANY_ATTEMPTS");
  const user = await env.DB.prepare("SELECT user_id, tenant_id, password_hash FROM users WHERE email = ?1").bind(mail).first();
  const ok = user && typeof password === "string" && (await verifyPassword(password, user.password_hash));
  if (!ok) {
    await env.DB.prepare("INSERT INTO login_attempts (email, attempted_at) VALUES (?1, ?2)").bind(mail, t).run();
    throw new HttpError(401, "INVALID_CREDENTIALS");
  }
  return startSession(env, user.user_id, user.tenant_id);
}

export async function logout(request, env) {
  const token = cookieValue(request, COOKIE);
  if (token) await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?1").bind(await sha256hex(token)).run();
  return json({ status: "ok" }, 200, { "Set-Cookie": sessionCookie("", 0) });
}

export async function me(request, env) {
  const s = await currentSession(request, env);
  const t = now();
  const ents = await env.DB.prepare(
    "SELECT plan, starts_at, ends_at, features FROM entitlements WHERE tenant_id = ?1 ORDER BY ends_at DESC"
  ).bind(s.tenant_id).all();
  const active = (ents.results || []).filter((e) => e.starts_at <= t && e.ends_at > t);
  return json({
    email: s.email,
    email_verified: Boolean(s.email_verified_at),
    plan: active[0]?.plan || "none",
    plan_ends_at: active[0]?.ends_at || null,
    features: [...new Set(active.flatMap((e) => JSON.parse(e.features)))],
    live_trading: "disabled",
  });
}

export async function verifyEmail(request, env) {
  const { token } = await readJson(request, ["token"]);
  const userId = await consumeEmailToken(env, token, "verify");
  await env.DB.prepare("UPDATE users SET email_verified_at = ?1 WHERE user_id = ?2 AND email_verified_at IS NULL")
    .bind(now(), userId).run();
  return json({ status: "verified" });
}

export async function resendVerification(request, env) {
  const s = await currentSession(request, env);
  if (s.email_verified_at) return json({ status: "already_verified" });
  const last = await env.DB.prepare(
    "SELECT MAX(created_at) AS t FROM email_tokens WHERE user_id = ?1 AND purpose = 'verify'"
  ).bind(s.user_id).first();
  if (last && last.t && now() - last.t < 60) throw new HttpError(429, "WAIT_BEFORE_RESEND");
  await sendVerification(env, s.user_id, s.email);
  return json({ status: "sent" });
}

export async function forgotPassword(request, env) {
  const { email, turnstile_token } = await readJson(request, ["email", "turnstile_token"]);
  await verifyTurnstile(env, turnstile_token, request);
  const mail = String(email || "").trim().toLowerCase();
  const user = EMAIL_RE.test(mail)
    ? await env.DB.prepare("SELECT user_id FROM users WHERE email = ?1").bind(mail).first() : null;
  if (user) {
    const last = await env.DB.prepare(
      "SELECT MAX(created_at) AS t FROM email_tokens WHERE user_id = ?1 AND purpose = 'reset'"
    ).bind(user.user_id).first();
    if (!(last && last.t && now() - last.t < 60)) {
      const token = await issueEmailToken(env, user.user_id, "reset", RESET_TTL);
      await sendEmail(env, mail, "Réinitialisation du mot de passe · Hinova Trading Lab",
        `Pour choisir un nouveau mot de passe, ouvrez ce lien (valable 30 minutes) :\n${link(env, "reset", token)}\n\n` +
        "Si vous n'avez rien demandé, ignorez ce message : votre mot de passe reste inchangé.");
    }
  }
  return json({ status: "ok" });       // identical answer whether or not the account exists
}

export async function resetPassword(request, env) {
  const { token, password } = await readJson(request, ["token", "password"]);
  checkPassword(password);
  const userId = await consumeEmailToken(env, token, "reset");
  const hash = await hashPassword(password, Number(env.PBKDF2_ITERATIONS || 100000));
  await env.DB.batch([
    env.DB.prepare("UPDATE users SET password_hash = ?1, email_verified_at = COALESCE(email_verified_at, ?2) WHERE user_id = ?3")
      .bind(hash, now(), userId),                    // receiving the link proves control of the address
    env.DB.prepare("DELETE FROM sessions WHERE user_id = ?1").bind(userId),
    env.DB.prepare("DELETE FROM login_attempts WHERE email = (SELECT email FROM users WHERE user_id = ?1)").bind(userId),
  ]);
  return json({ status: "password_updated" });
}
