// Rendering only: each function maps server data to markup. No signal math.
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtTs = (ts) => ts ? new Date(ts * 1000).toISOString().replace("T", " ").slice(0, 16) + " UTC" : "—";
const num = (v, d = 2) => (v === null || v === undefined) ? "—" : (typeof v === "number" ? v.toFixed(d) : esc(v));
const tone = (d) => ({ BUY: "buy", SELL: "sell" }[d] || "");
const PROFILE_ORDER = ["scalping", "intraday", "swing", "custom"];

export function modeBadges(snap) {
  const s = snap.latest_signal;
  return `<span class="badge" data-tone="accent">Mode ${esc(s.mode)}</span>
    <span class="badge" data-tone="warn">Live désactivé</span>
    ${snap.snapshot_kind.includes("SYNTHETIC") ? '<span class="badge" data-tone="gold">Démo synthétique</span>' : ""}`;
}

export function profileSwitch(snap, current) {
  return PROFILE_ORDER.filter((p) => snap.profiles[p]).map((p) =>
    `<button type="button" data-profile="${p}" aria-pressed="${p === current}">${esc(snap.profiles[p].label)}</button>`).join("");
}

export function profileDetails(p) {
  const tf = p.timeframes;
  return `<dt>Biais / setup / trigger</dt><dd>${esc(tf.bias)} / ${esc(tf.setup)} / ${esc(tf.trigger)}</dd>
    <dt>Session</dt><dd>${p.session_utc.start_hour}h–${p.session_utc.end_hour}h UTC</dd>
    <dt>Fraîcheur max</dt><dd>${p.max_data_age_seconds}s</dd>
    <dt>Spread max</dt><dd>${num(p.max_spread)}</dd>
    <dt>Coûts modélisés</dt><dd>spr ${num(p.costs.spread)} · slip ${num(p.costs.slippage)} · comm ${num(p.costs.commission)}</dd>
    <dt>Détention max</dt><dd>${p.max_holding_bars} barres</dd>
    <dt>Risque / trade</dt><dd>${num(p.risk.max_risk_per_trade_pct)} %</dd>
    <dt>Positions max</dt><dd>${p.risk.max_open_positions}</dd>
    <dt>Perte jour max</dt><dd>${num(p.risk.max_daily_loss_pct)} %</dd>
    <dt>Mode</dt><dd>${esc(p.mode)}</dd>`;
}

export function strategyList(snap, draft) {
  const profile = snap.profiles[draft.profile];
  return snap.catalog.map((s) => {
    const eligible = profile.eligible_strategies.includes(s.strategy_id);
    const on = draft.enabled.has(s.strategy_id) && eligible && s.available;
    const disabled = !s.available || !eligible;
    const why = !s.available ? `indisponible · ${esc(s.unavailable_reason)}` : (!eligible ? "non éligible à ce profil" : esc(s.role === "filter" ? "filtre (peut seulement bloquer)" : "signal"));
    const params = s.params.map((p) => `${p.name}=${p.default}`).slice(0, 3).join(" ");
    return `<li class="strategy" data-on="${on}" data-eligible="${eligible}" data-available="${s.available}">
      <span class="strategy-name">${esc(s.name)}</span>
      <label class="switch" title="${why}">
        <input type="checkbox" data-strategy="${esc(s.strategy_id)}" ${on ? "checked" : ""} ${disabled ? "disabled" : ""}
          aria-label="Activer ${esc(s.name)}">
        <span class="switch-track"></span>
      </label>
      <span class="strategy-sub">${esc(s.strategy_id)} v${esc(s.version)} · ${why}${params ? " · " + esc(params) : ""}</span>
    </li>`;
  }).join("");
}

export function decision(sig) {
  const codes = sig.reason_codes.filter((c) => !c.startsWith("AGGREGATION")).map((c) => `<span class="badge">${esc(c)}</span>`).join("");
  return `<div class="decision-value">${esc(sig.decision)}</div>
    <div class="badge-row">
      <span class="badge" data-tone="${sig.risk_status === "allowed" ? "buy" : "warn"}">risque : ${esc(sig.risk_status)}</span>
      <span class="badge" data-tone="warn">exécution autorisée : ${sig.execution_allowed ? "oui" : "non"}</span>
      <span class="badge">données : ${esc(sig.data_status)}</span>
    </div>
    <div class="badge-row">${codes}</div>
    <dl class="kv"><dt>Config</dt><dd>${esc(sig.config_hash)}</dd><dt>Données</dt><dd>${esc(sig.data_hash)}</dd>
      <dt>Stratégies</dt><dd>${esc(sig.strategy_ids.join(", "))}</dd></dl>`;
}

export function chart(candles, signals, el) {
  const W = el.clientWidth || 640, H = 260, pad = { l: 8, r: 52, t: 10, b: 20 };
  const hi = Math.max(...candles.map((c) => c.h)), lo = Math.min(...candles.map((c) => c.l));
  const x = (i) => pad.l + (i + 0.5) * ((W - pad.l - pad.r) / candles.length);
  const y = (v) => pad.t + (hi - v) / (hi - lo || 1) * (H - pad.t - pad.b);
  const bw = Math.max(1, (W - pad.l - pad.r) / candles.length * 0.6);
  const grid = [0, .25, .5, .75, 1].map((f) => {
    const v = lo + (hi - lo) * f, yy = y(v);
    return `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${yy}" y2="${yy}"/><text class="axis" x="${W - pad.r + 6}" y="${yy + 3}">${v.toFixed(1)}</text>`;
  }).join("");
  const idx = new Map(candles.map((c, i) => [c.ts, i]));
  const bars = candles.map((c, i) => {
    const cls = c.c >= c.o ? "up" : "down", top = y(Math.max(c.o, c.c)), h = Math.max(1, Math.abs(y(c.o) - y(c.c)));
    return `<line class="wick ${cls}" x1="${x(i)}" x2="${x(i)}" y1="${y(c.h)}" y2="${y(c.l)}"/><rect class="${cls}" x="${x(i) - bw / 2}" y="${top}" width="${bw}" height="${h}"/>`;
  }).join("");
  const marks = signals.filter((s) => idx.has(s.ts)).map((s) => {
    const i = idx.get(s.ts), c = candles[i], buy = s.decision === "BUY";
    const yy = buy ? y(c.l) + 10 : y(c.h) - 10, d = buy ? 6 : -6;
    return `<path class="${buy ? "mark-buy" : "mark-sell"}" d="M${x(i)} ${yy - d} l5 ${d} h-10z"><title>${s.decision} ${fmtTs(s.ts)}</title></path>`;
  }).join("");
  el.setAttribute("viewBox", `0 0 ${W} ${H}`);
  el.innerHTML = grid + bars + marks;
}

export function evidenceTable(sig) {
  const rows = sig.strategy_results.flatMap((r) => r.evidence.map((e) =>
    `<tr><td>${esc(r.strategy_id)}</td><td>${esc(e.kind)}</td><td>${esc(e.name)}</td><td class="num">${num(e.value, 4)}</td><td>${fmtTs(e.candle_ts)}</td><td class="muted">${esc(e.evidence_id)}</td></tr>`));
  if (!rows.length) return `<p class="empty">Aucune preuve : pas de signal possible.</p>`;
  return `<table class="table"><thead><tr><th>Stratégie</th><th>Type</th><th>Nom</th><th class="num">Valeur</th><th>Bougie</th><th>ID</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

export function dataState(snap, sig) {
  const p = snap.provenance;
  return `<dt>Symbole</dt><dd>${esc(p.symbol)}</dd><dt>Instrument</dt><dd>${esc(p.instrument_type)}</dd>
    <dt>Timeframe</dt><dd>${esc(p.timeframe)}</dd><dt>Source</dt><dd>${esc(p.source)}</dd>
    <dt>Bougies</dt><dd>${p.candles}</dd><dt>Qualité</dt><dd>${esc(p.quality)}</dd>
    <dt>Statut signal</dt><dd>${esc(sig.data_status)}</dd><dt>Dernière bougie</dt><dd>${fmtTs(sig.as_of_ts)}</dd>`;
}

export function riskPanel(sig) {
  const v = sig.veto_codes.map((c) => `<span class="badge" data-tone="warn">${esc(c)}</span>`).join("") || '<span class="badge" data-tone="buy">aucun veto</span>';
  return `<div class="badge-row">${v}</div>
    <p class="muted">Le moteur de risque est déterministe et indépendant : il peut bloquer une proposition même si toutes les stratégies et tous les agents sont d'accord. Aucun ordre n'est transmis.</p>`;
}

export function recentSignals(list) {
  if (!list.length) return `<p class="empty">Aucun signal sur la période.</p>`;
  return `<table class="table"><thead><tr><th>Heure</th><th>Décision</th><th class="num">Clôture</th></tr></thead><tbody>${
    list.slice().reverse().map((s) => `<tr><td>${fmtTs(s.ts)}</td><td><span class="badge" data-tone="${tone(s.decision)}">${esc(s.decision)}</span></td><td class="num">${num(s.price)}</td></tr>`).join("")}</tbody></table>`;
}

export function performance(perf) {
  const rows = Object.entries(perf).flatMap(([sid, m]) => ["all", "in_sample", "out_of_sample"].map((seg) => {
    const r = m[seg], cls = r.expectancy > 0 ? "pos" : (r.expectancy < 0 ? "neg" : "");
    return `<tr><td>${seg === "all" ? esc(sid) : ""}</td><td>${{ all: "total", in_sample: "IS", out_of_sample: "OOS" }[seg]}</td>
      <td class="num">${r.trades}</td><td class="num ${cls}">${num(r.expectancy)}</td><td class="num">${num(r.profit_factor)}</td>
      <td class="num">${num(r.max_drawdown_points)}</td><td>${r.sample_warning ? `<span class="badge" data-tone="warn">${esc(r.sample_warning)}</span>` : ""}</td></tr>`;
  }));
  return `<table class="table"><thead><tr><th>Stratégie</th><th>Segment</th><th class="num">Trades</th><th class="num">Espérance</th><th class="num">PF</th><th class="num">Max DD</th><th></th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

export function agents(review) {
  if (!review) return `<p class="empty">Revue non disponible. Le moteur fonctionne sans IA.</p>`;
  if (review.status !== "accepted") return `<p class="empty">Revue rejetée (${esc(review.error)}). Décision déterministe inchangée.</p>`;
  return review.outputs.map((o) => `<div class="agent"><span class="agent-role">${esc(o.role)}</span>
    <div class="badge-row"><span class="badge" data-tone="${o.stance === "support" ? "accent" : (o.stance === "oppose" ? "warn" : "")}">${esc(o.stance)}</span>
      ${o.claims.map((c) => `<span class="badge">${esc(c.code)} · ${c.evidence_ids.length} preuve(s)</span>`).join("")}
      ${o.rejection_reasons.map((r) => `<span class="badge" data-tone="warn">${esc(r)}</span>`).join("")}</div></div>`).join("") +
    `<p class="muted">Source : ${esc(review.source)}. Consultatif uniquement.</p>`;
}
