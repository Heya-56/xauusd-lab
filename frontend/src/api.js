const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
// Chaque requête est abandonnée au bout de 4 s : une API lente ne peut plus figer l'écran.
const withTimeout = (ms = 4000) => { const c = new AbortController(); setTimeout(() => c.abort(), ms); return c.signal }
export async function get(path) {
  const r = await fetch(BASE + path, { cache: 'no-store', signal: withTimeout() })
  if (!r.ok) { let m = await r.text(); try { m = JSON.parse(m).detail || m } catch {} ; throw new Error(m) }
  return r.json()
}
export async function post(path, body, token) {
  const r = await fetch(BASE + path, { method: 'POST', signal: withTimeout(8000), headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Admin-Token': token } : {}) }, body: JSON.stringify(body) })
  if (!r.ok) { let m = await r.text(); try { m = JSON.parse(m).detail || m } catch {} ; throw new Error(m) }
  return r.json()
}
