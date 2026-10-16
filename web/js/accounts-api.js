// Accounts API client. No trading logic. Session lives in an HttpOnly cookie.
const BASE = (window.HINOVA_ACCOUNTS_API || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}

async function req(method, path, body) {
  if (!BASE) throw new ApiError(0, "API_NOT_CONFIGURED");
  let res;
  try {
    res = await fetch(BASE + path, {
      method, credentials: "include",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.error || "UNKNOWN_ERROR");
  return data;
}

const withCaptcha = (o, token) => (token ? { ...o, turnstile_token: token } : o);

export const api = {
  base: BASE,
  signup: (email, password, captcha) => req("POST", "/v1/auth/signup", withCaptcha({ email, password }, captcha)),
  login: (email, password) => req("POST", "/v1/auth/login", { email, password }),
  logout: () => req("POST", "/v1/auth/logout"),
  me: () => req("GET", "/v1/me"),
  verify: (token) => req("POST", "/v1/auth/verify", { token }),
  resendVerification: () => req("POST", "/v1/auth/verify/resend"),
  forgot: (email, captcha) => req("POST", "/v1/auth/password/forgot", withCaptcha({ email }, captcha)),
  reset: (token, password) => req("POST", "/v1/auth/password/reset", { token, password }),
  terminals: () => req("GET", "/v1/terminals"),
  createTerminal: (label) => req("POST", "/v1/terminals", { label }),
  revokeTerminal: (id) => req("DELETE", `/v1/terminals/${encodeURIComponent(id)}`),
};
