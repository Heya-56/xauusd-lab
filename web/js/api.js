// Data access only. The browser never computes signals; it reads server output.
// No API configured, or not signed in => offline demo on the synthetic snapshot.
export const API_BASE = (window.HINOVA_ACCOUNTS_API || window.HINOVA_API_BASE || "").replace(/\/$/, "");

async function demo(reason) {
  const res = await fetch("data/demo-snapshot.json", { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`snapshot ${res.status}`);
  return { ...(await res.json()), demo_reason: reason };
}

export async function loadSnapshot() {
  if (!API_BASE) return demo("API_NOT_CONFIGURED");
  let res;
  try {
    res = await fetch(`${API_BASE}/v1/dashboard`, { headers: { Accept: "application/json" }, credentials: "include" });
  } catch {
    return demo("NETWORK_ERROR");
  }
  if (res.status === 401) return demo("NOT_SIGNED_IN");
  if (!res.ok) throw new Error(`dashboard ${res.status}`);
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
