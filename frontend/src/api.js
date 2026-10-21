const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
export async function get(path) {
  const r = await fetch(BASE + path, { cache: 'no-store' })
  if (!r.ok) throw new Error(r.status + ' ' + (await r.text()))
  return r.json()
}
export async function post(path, body, token) {
  const r = await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Admin-Token': token } : {}) }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(r.status + ' ' + (await r.text()))
  return r.json()
}
