// Shared helpers: crypto, HTTP, cookies, origin checks. No business logic.
export const DAY = 86400;
export const enc = new TextEncoder();

export const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
export const fromB64url = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
export const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
export const randomToken = (bytes = 32) => b64url(crypto.getRandomValues(new Uint8Array(bytes)));
export const sha256hex = async (s) => hex(await crypto.subtle.digest("SHA-256", enc.encode(s)));
export const now = () => Math.floor(Date.now() / 1000);

export function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

export async function hmacHex(secret, message) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
}

export class HttpError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}

export function json(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
               "X-Content-Type-Options": "nosniff", ...headers },
  });
}

export async function readJson(request, allowed, maxBytes = 4096) {
  if (!(request.headers.get("Content-Type") || "").startsWith("application/json")) {
    throw new HttpError(415, "JSON_REQUIRED");
  }
  const text = await request.text();
  if (text.length > maxBytes) throw new HttpError(413, "BODY_TOO_LARGE");
  let body;
  try { body = JSON.parse(text); } catch { throw new HttpError(400, "INVALID_JSON"); }
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new HttpError(400, "BODY_NOT_OBJECT");
  if (allowed) {
    const extra = Object.keys(body).filter((k) => !allowed.includes(k));
    if (extra.length) throw new HttpError(400, `UNKNOWN_FIELDS:${extra.join(",")}`);
  }
  return body;
}

export function cookieValue(request, name) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

export const allowedOrigins = (env) => (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
export const isDev = (env) => env.DEV_MODE === "true";
