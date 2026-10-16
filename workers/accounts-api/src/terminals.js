// MT5 terminal keys: created once, stored as sha256, revocable, max 3 per tenant.
import { HttpError, json, now, randomToken, readJson, sha256hex } from "./lib.js";
import { currentSession } from "./auth.js";

const MAX_TERMINALS = 3;

export async function listTerminals(request, env) {
  const s = await currentSession(request, env);
  const rows = await env.DB.prepare(
    "SELECT terminal_id, label, key_prefix, created_at, last_seen_at FROM terminals " +
    "WHERE tenant_id = ?1 AND revoked_at IS NULL ORDER BY created_at"
  ).bind(s.tenant_id).all();
  return json({ terminals: rows.results || [], max: MAX_TERMINALS });
}

export async function createTerminal(request, env) {
  const s = await currentSession(request, env);
  if (!s.email_verified_at) throw new HttpError(403, "EMAIL_NOT_VERIFIED");
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
  return json({ terminal_id: id, label: name, api_key: key, shown_once: true }, 201);
}

export async function revokeTerminal(request, env, terminalId) {
  const s = await currentSession(request, env);
  const res = await env.DB.prepare(
    "UPDATE terminals SET revoked_at = ?1 WHERE terminal_id = ?2 AND tenant_id = ?3 AND revoked_at IS NULL"
  ).bind(now(), terminalId, s.tenant_id).run();
  if (!res.meta || res.meta.changes === 0) throw new HttpError(404, "TERMINAL_NOT_FOUND");
  return json({ status: "revoked" });
}

export async function terminalFromKey(request, env) {
  const h = request.headers.get("Authorization") || "";
  const m = /^Bearer (htl_[A-Za-z0-9_-]{20,80})$/.exec(h);
  if (!m) throw new HttpError(401, "UNAUTHENTICATED");
  const row = await env.DB.prepare(
    "SELECT t.terminal_id, t.tenant_id, u.email_verified_at FROM terminals t " +
    "JOIN users u ON u.tenant_id = t.tenant_id WHERE t.key_hash = ?1 AND t.revoked_at IS NULL"
  ).bind(await sha256hex(m[1])).first();
  if (!row) throw new HttpError(401, "UNAUTHENTICATED");
  return row;
}
