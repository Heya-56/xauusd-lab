// Client view: plain-language rendering of the same server snapshot. No signal math in the browser.
import { loadSnapshot } from "./api.js";
import { chart } from "./components.js";

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const when = (ts) => ts ? new Date(ts * 1000).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
const ago = (ts) => {
  if (!ts) return "";
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  if (m < 1440) return `il y a ${Math.round(m / 60)} h`;
  return `il y a ${Math.round(m / 1440)} j`;
};

// Engine codes -> sentences a client understands. Unknown codes fall back to a neutral sentence.
const WHY = {
  NO_STRATEGY_ENABLED: "Aucune méthode n'est activée dans vos réglages.",
  NO_VALID_SIGNAL: "Les méthodes ne voient pas d'occasion claire.",
  NO_PROPOSAL: "Les méthodes ne voient pas d'occasion claire.",
  INSUFFICIENT_AGREEMENT: "Les méthodes ne sont pas d'accord entre elles.",
  FILTER_BLOCK: "Un filtre de sécurité demande d'attendre.",
  OUTSIDE_SESSION: "Le marché est hors des heures choisies pour votre style.",
  SPREAD_TOO_WIDE: "L'écart de prix chez votre broker est trop large en ce moment.",
  SPREAD_UNKNOWN: "L'écart de prix du broker n'est pas connu.",
  NO_VALID_STOP: "Impossible de placer un stop raisonnable.",
  STOP_TOO_TIGHT_VS_SPREAD: "Le stop serait trop proche par rapport à l'écart de prix.",
  RISK_PER_TRADE_EXCEEDED: "Le risque dépasserait votre limite par position.",
  MAX_OPEN_POSITIONS: "Vous avez déjà le nombre maximum de positions.",
  DAILY_LOSS_LIMIT: "La limite de perte du jour est atteinte : pause jusqu'à demain.",
  TIMEFRAME_PROFILE_MISMATCH: "L'unité de temps de l'EA ne correspond pas à votre style.",
  SYNTHETIC_FIXTURE_NOT_MARKET_DATA: "Ce sont des données de démonstration, pas le vrai marché.",
  LIVE_EXECUTION_DISABLED: null,               // always true by design, shown in the footer instead
  FILTER_PASS: null,
};
const STYLE_TEXT = {
  scalping: "Scalping : positions très courtes (minutes), beaucoup de petits mouvements, demande d'être disponible.",
  intraday: "Intraday : positions de quelques heures, fermées dans la journée. Le bon équilibre pour démarrer.",
  swing: "Swing : positions de plusieurs jours, moins de signaux, plus de patience.",
  custom: "Personnalisé : réglages sur mesure.",
};

function hero(sig, snap) {
  const map = {
    BUY:  ["buy",  "Signal d'achat", "Les méthodes voient une occasion d'achat sur l'or."],
    SELL: ["sell", "Signal de vente", "Les méthodes voient une occasion de vente sur l'or."],
  };
  const [tone, title, text] = map[sig.decision] || ["wait", "On attend", "Pas d'occasion assez sûre pour l'instant. Attendre fait partie de la stratégie."];
  const blocked = sig.decision !== "NO_TRADE" && sig.risk_status !== "allowed";
  $("c-hero").dataset.tone = blocked ? "wait" : tone;
  $("c-hero-title").textContent = blocked ? `${title} — bloqué par la sécurité` : title;
  $("c-hero-text").textContent = blocked ? "Une occasion est détectée, mais une règle de sécurité l'empêche." : text;

  const codes = [...new Set([...(sig.veto_codes || []), ...(sig.reason_codes || [])])]
    .filter((c) => !c.startsWith("AGGREGATION"));
  const reasons = [...new Set(codes.map((c) => (c in WHY ? WHY[c] : "Une condition technique n'est pas remplie.")).filter(Boolean))];
  $("c-why").innerHTML = reasons.slice(0, 4).map((r) => `<li>${esc(r)}</li>`).join("");

  const res = (sig.strategy_results || []).find((r) => r.decision === sig.decision && r.stop_distance);
  const levels = res && sig.decision !== "NO_TRADE"
    ? ` · stop indicatif à ${res.stop_distance.toFixed(2)} $ · objectif à ${res.target_distance.toFixed(2)} $` : "";
  $("c-hero-foot").textContent = `Mis à jour ${ago(sig.as_of_ts)} (${when(sig.as_of_ts)})${levels}. Vous restez seul décideur.`;
}

function light(el, ok, title, text) {
  el.dataset.state = ok === true ? "ok" : ok === false ? "ko" : "info";
  el.innerHTML = `<span class="c-light-dot" aria-hidden="true"></span><div><div class="c-light-title">${esc(title)}</div><div class="c-light-text">${esc(text)}</div></div>`;
}

function lights(snap, sig) {
  const live = snap.snapshot_kind === "LIVE";
  const fresh = sig.as_of_ts && (Date.now() / 1000 - sig.as_of_ts) < 2 * 3600;
  light($("c-l-mt5"), live ? (fresh ? true : false) : null, "MetaTrader 5",
    live ? (fresh ? "Connecté, prix reçus récemment." : "Aucun prix reçu depuis un moment. MT5 est-il ouvert ?") : "Mode démonstration (non connecté).");
  light($("c-l-data"), sig.data_status === "valid" ? true : false, "Données",
    sig.data_status === "valid" ? "Prix complets et vérifiés." : "Données incomplètes : aucun signal n'est donné.");
  light($("c-l-safety"), true, "Sécurité", "Aucun ordre automatique. Vos fonds ne sont jamais touchés.");
}

function gauges(perf, catalog) {
  const names = Object.fromEntries((catalog || []).map((s) => [s.strategy_id, s.name]));
  const rows = Object.entries(perf || {}).map(([sid, m]) => ({ sid, name: names[sid] || sid, sc: m.score || {}, oos: m.out_of_sample || {} }))
    .sort((a, b) => (b.sc.score ?? 0) - (a.sc.score ?? 0));
  if (!rows.length) return `<p class="empty">Pas encore de note : il faut des données réelles.</p>`;
  const label = { RETAINED: "Retenue", WATCH: "À surveiller", REJECTED: "Écartée" };
  const gateText = { SYNTHETIC_DATA: "données de démo", INSUFFICIENT_SAMPLE: "trop peu de trades", INSUFFICIENT_OOS: "pas assez testée", OOS_NOT_PROFITABLE: "perd sur les nouvelles périodes" };
  return rows.map(({ sid, name, sc, oos }) => {
    const s = Math.max(0, Math.min(10, sc.score ?? 0));
    const tier = sc.tier || "REJECTED";
    const note = (sc.gates || []).map((g) => gateText[g] || g).join(", ");
    return `<div class="c-gauge" data-tier="${esc(tier)}">
      <div class="c-gauge-head"><span class="c-gauge-name">${esc(name)}</span><span class="c-gauge-score">${s.toFixed(1)}<small>/10</small></span></div>
      <div class="c-bar" role="meter" aria-valuemin="0" aria-valuemax="10" aria-valuenow="${s}" aria-label="${esc(name)}">
        <span style="width:${s * 10}%"></span><i style="left:50%"></i><i style="left:60%"></i>
      </div>
      <div class="c-gauge-foot"><span class="c-tag">${label[tier] || esc(tier)}</span>
        <span>${oos.trades ?? 0} trade${(oos.trades ?? 0) > 1 ? "s" : ""} testé${(oos.trades ?? 0) > 1 ? "s" : ""}${oos.win_rate_pct != null ? ` · ${Math.round(oos.win_rate_pct)} % gagnants` : ""}</span>
        ${note ? `<span class="c-note">${esc(note)}</span>` : ""}</div>
    </div>`;
  }).join("");
}

function history(list) {
  if (!list || !list.length) return `<li class="empty">Aucun signal récent.</li>`;
  const word = { BUY: "Achat", SELL: "Vente" };
  return list.slice().reverse().slice(0, 8).map((s) =>
    `<li data-tone="${s.decision === "BUY" ? "buy" : s.decision === "SELL" ? "sell" : "wait"}">
      <span class="c-h-word">${esc(word[s.decision] || "Attente")}</span>
      <span class="c-h-price">${s.price != null ? s.price.toFixed(2) + " $" : ""}</span>
      <span class="c-h-time">${when(s.ts)}</span></li>`).join("");
}

function styles(snap) {
  const cur = snap.active_config?.profile || snap.latest_signal?.profile;
  $("c-styles").innerHTML = ["scalping", "intraday", "swing", "custom"].filter((p) => snap.profiles?.[p]).map((p) =>
    `<span class="c-style" aria-current="${p === cur}">${esc(snap.profiles[p].label)}</span>`).join("");
  $("c-style-text").textContent = STYLE_TEXT[cur] || "";
}

async function main() {
  let snap;
  try { snap = await loadSnapshot(); }
  catch {
    $("c-hero").dataset.tone = "wait";
    $("c-hero-title").textContent = "Service momentanément indisponible";
    $("c-hero-text").textContent = "Aucun signal n'est affiché tant que les données ne sont pas chargées. Réessayez dans quelques minutes.";
    return;
  }
  const sig = snap.latest_signal;
  if (snap.snapshot_kind !== "LIVE") {
    $("c-banner").hidden = false;
    $("c-banner").textContent = snap.demo_reason === "NOT_SIGNED_IN"
      ? "Démonstration avec des prix fictifs. Connectez-vous dans « Mon compte » pour voir vos propres signaux."
      : "Démonstration avec des prix fictifs : ce ne sont pas des résultats réels.";
  }
  hero(sig, snap);
  lights(snap, sig);
  $("c-gauges").innerHTML = gauges(snap.performance, snap.catalog);
  $("c-history").innerHTML = history(snap.recent_signals);
  styles(snap);
  $("c-chart-meta").textContent = `${snap.provenance.timeframe} · ${snap.provenance.candles} bougies`;
  const draw = () => chart(snap.candles, snap.recent_signals, $("c-chart"));
  draw();
  window.addEventListener("resize", draw);
}

main();
