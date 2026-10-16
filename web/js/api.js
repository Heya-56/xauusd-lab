// Data access only. The browser never computes signals; it reads server output.
// API_BASE empty => offline demo mode reading the synthetic snapshot.
export const API_BASE = (window.HINOVA_API_BASE || "").replace(/\/$/, "");

export async function loadSnapshot() {
  const url = API_BASE ? `${API_BASE}/v1/dashboard` : "data/demo-snapshot.json";
  const res = await fetch(url, { headers: { Accept: "application/json" }, credentials: "include" });
  if (!res.ok) throw new Error(`snapshot ${res.status}`);
  return res.json();
}

// Sends a configuration (never code) to PUT /v1/config. The server validates
// params, eligibility, availability and risk ceilings; the UI cannot bypass it.
export async function submitConfig(config) {
  if (!API_BASE) return { status: "offline", message: "API non connectée : aucune modification enregistrée." };
  const res = await fetch(`${API_BASE}/v1/config`, {
    method: "PUT", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const body = await res.json().catch(() => ({}));
  return { status: res.ok ? "stored" : "rejected", http: res.status, ...body };
}
