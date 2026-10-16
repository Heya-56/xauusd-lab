import { loadSnapshot, submitConfig } from "./api.js";
import * as C from "./components.js";
import { createState } from "./state.js";

const $ = (id) => document.getElementById(id);

async function main() {
  let snap;
  try {
    snap = await loadSnapshot();
  } catch (err) {
    $("data-banner").hidden = false;
    $("data-banner").textContent = "Impossible de charger les données. Aucune décision affichée (NO_TRADE par défaut).";
    return;
  }
  const state = createState(snap);
  const sig = snap.latest_signal;

  $("mode-badges").innerHTML = C.modeBadges(snap);
  if (snap.disclaimer) { $("data-banner").hidden = false; $("data-banner").textContent = snap.disclaimer; }
  $("decision").dataset.decision = sig.decision;
  $("decision").innerHTML = C.decision(sig);
  $("dec-time").textContent = `profil ${sig.profile} · ${sig.timeframe}`;
  $("evidence").innerHTML = C.evidenceTable(sig);
  $("data-state").innerHTML = C.dataState(snap, sig);
  $("risk").innerHTML = C.riskPanel(sig);
  $("recent-signals").innerHTML = C.recentSignals(snap.recent_signals);
  $("performance").innerHTML = C.performance(snap.performance);
  $("agents").innerHTML = C.agents(sig.agent_review);
  $("chart-meta").textContent = `${snap.provenance.symbol} · ${snap.provenance.timeframe} · ${snap.provenance.instrument_type}`;
  const drawChart = () => C.chart(snap.candles, snap.recent_signals, $("chart"));
  drawChart();
  window.addEventListener("resize", drawChart);

  const renderConfig = () => {
    $("profile-switch").innerHTML = C.profileSwitch(snap, state.draft.profile);
    $("profile-details").innerHTML = C.profileDetails(snap.profiles[state.draft.profile]);
    $("strategy-list").innerHTML = C.strategyList(snap, state.draft);
    $("strat-count").textContent = `${state.draft.enabled.size} actives`;
    const dirty = state.isDirty();
    $("draft-bar").hidden = !dirty;
    $("draft-text").textContent = "Configuration modifiée localement — la validation serveur est requise avant toute prise en compte.";
  };
  state.subscribe(renderConfig);
  renderConfig();

  $("profile-switch").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-profile]");
    if (b) state.setProfile(b.dataset.profile);
  });
  $("strategy-list").addEventListener("change", (e) => {
    const input = e.target.closest("input[data-strategy]");
    if (input) state.toggle(input.dataset.strategy, input.checked);
  });
  $("draft-reset").addEventListener("click", () => { $("draft-payload").hidden = true; state.reset(); });
  $("draft-submit").addEventListener("click", async () => {
    const payload = state.payload();
    const res = await submitConfig(payload);
    $("draft-payload").hidden = false;
    $("draft-payload").textContent = JSON.stringify({ request: payload, response: res }, null, 2);
  });
}

main();
