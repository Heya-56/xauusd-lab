// Draft configuration state. Holds user choices only — no trading logic.
export function createState(snapshot) {
  const saved = { profile: snapshot.active_config.profile, enabled: new Set(snapshot.active_config.enabled) };
  const draft = { profile: saved.profile, enabled: new Set(saved.enabled) };
  const listeners = new Set();
  const emit = () => listeners.forEach((fn) => fn());
  return {
    snapshot, saved, draft,
    subscribe(fn) { listeners.add(fn); },
    setProfile(p) { draft.profile = p; emit(); },
    toggle(id, on) { on ? draft.enabled.add(id) : draft.enabled.delete(id); emit(); },
    reset() { draft.profile = saved.profile; draft.enabled = new Set(saved.enabled); emit(); },
    isDirty() {
      return draft.profile !== saved.profile || draft.enabled.size !== saved.enabled.size ||
        [...draft.enabled].some((x) => !saved.enabled.has(x));
    },
    // Payload for PUT /v1/config. Ineligible strategies are still sent if the user
    // forced them via devtools: the server rejects them.
    payload() {
      return { profile: draft.profile,
        strategies: Object.fromEntries(snapshot.catalog.map((s) => [s.strategy_id, { enabled: draft.enabled.has(s.strategy_id) }])) };
    },
  };
}
