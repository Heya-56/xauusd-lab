// Base de l'API : même origine par défaut (l'interface est servie par FastAPI sur /ui/),
// ou VITE_API_URL au build pour une interface hébergée ailleurs (Cloudflare Pages).
const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json() as Promise<T>
}

export async function post<T>(path: string, body: unknown, adminToken?: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(adminToken ? { 'X-Admin-Token': adminToken } : {}) },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json() as Promise<T>
}

export type Signal = { agent: string; lang: string; action: string; entry?: number; stop_loss?: number; tp1?: number; tp2?: number; reason: string; timestamp: string }
export type Bar = { ts: string; open: number; high: number; low: number; close: number }
export type Kill = { engaged: boolean; reason?: string; at?: string }
export type Consensus = { direction: string; score: number; agents: number; bar_ts?: string }
export type Market = { symbol: string; bid?: number; ask?: number; timestamp?: string }
export type Status = { mode: string; strategy: string; account: { equity: number; realized_today: number; trades_today: number } | null; position: unknown }
