// Hinova Trading Lab — accounts & gateway API (Cloudflare Worker + D1).
//
// Scope: accounts, sessions, trial, e-mail verification, password reset, MT5 terminal
// keys, the EA signal gateway, strategy configuration and the dashboard snapshot.
// Out of scope by design: strategy maths, prices, orders. Signals come only from the
// deterministic Python engine (ENGINE_URL), called with an HMAC-signed request.
import { HttpError, allowedOrigins, json } from "./lib.js";
import * as auth from "./auth.js";
import * as terminals from "./terminals.js";
import * as signals from "./signals.js";

export { hashPassword, verifyPassword } from "./auth.js";

function checkOrigin(request, env, path) {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return;
  if (path === "/v1/ea/signal") return;                       // terminal-key auth, not a browser
  const origin = request.headers.get("Origin");
  if (!origin || !allowedOrigins(env).includes(origin)) throw new HttpError(403, "ORIGIN_NOT_ALLOWED");
}

const ROUTES = {
  "GET /v1/health": async () => json({ status: "ok", service: "accounts-api" }),
  "POST /v1/auth/signup": auth.signup,
  "POST /v1/auth/login": auth.login,
  "POST /v1/auth/logout": auth.logout,
  "POST /v1/auth/verify": auth.verifyEmail,
  "POST /v1/auth/verify/resend": auth.resendVerification,
  "POST /v1/auth/password/forgot": auth.forgotPassword,
  "POST /v1/auth/password/reset": auth.resetPassword,
  "GET /v1/me": auth.me,
  "GET /v1/terminals": terminals.listTerminals,
  "POST /v1/terminals": terminals.createTerminal,
  "POST /v1/ea/signal": signals.eaSignal,
  "GET /v1/config": signals.getConfig,
  "PUT /v1/config": signals.putConfig,
  "GET /v1/dashboard": signals.dashboard,
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin");
    const cors = origin && allowedOrigins(env).includes(origin)
      ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true", "Vary": "Origin" }
      : {};
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: { ...cors,
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE", "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "600" } });
    }
    try {
      const p = url.pathname, m = request.method;
      checkOrigin(request, env, p);
      let res;
      const handler = ROUTES[`${m} ${p}`];
      if (handler) res = await handler(request, env);
      else if (m === "DELETE" && /^\/v1\/terminals\/tm_[A-Za-z0-9_-]+$/.test(p)) res = await terminals.revokeTerminal(request, env, p.split("/")[3]);
      else res = json({ error: "NOT_FOUND" }, 404);
      for (const [k, v] of Object.entries(cors)) res.headers.set(k, v);
      return res;
    } catch (err) {
      if (err instanceof HttpError) return json({ error: err.code }, err.status, cors);
      return json({ error: "INTERNAL_ERROR" }, 500, cors);
    }
  },
};
