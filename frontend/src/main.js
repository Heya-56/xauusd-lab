import './ultron.scss'
import { get, post } from './api.js'
import { createOrb } from './orb.js'
import { createChart } from './chart.js'

const $ = (s) => document.querySelector(s)
const app = $('#app')
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
// Mode léger automatique sur les petites machines (≤ 4 Go ou ≤ 4 cœurs) : 20 i/s, effets coûteux coupés.
const lite = (navigator.deviceMemory && navigator.deviceMemory <= 4) || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4) || /lite/.test(location.search)
if (lite) document.body.classList.add('lite')
let still = reduced, frame = 0, ratio = 1, tf = 300, lastDraw = 0
const space = $('#space-canvas'), sctx = space.getContext('2d')
const orb = createOrb($('#orb-canvas'))
const chart = createChart($('#chart'))
const st = { kill: { engaged: false }, setups: [], online: false, price: null }
const fmt = (n, d = 2) => (n == null || Number.isNaN(n) ? '—' : Number(n).toFixed(d))

// ---------- fond étoilé ----------
const stars = Array.from({ length: lite ? 50 : 160 }, () => ({ x: Math.random(), y: Math.random(), z: Math.random(), s: Math.random() * 1.4 + .2, p: Math.random() * 6.28, v: Math.random() * .8 + .2 }))
function drawSpace(t) {
  const w = innerWidth, h = innerHeight
  sctx.clearRect(0, 0, w, h)
  for (const s of stars) {
    const x = ((s.x * w + (still ? 0 : t * .000018 * s.v) * w * .35) % w + w) % w
    sctx.beginPath(); sctx.fillStyle = `rgba(120,240,220,${.15 + (Math.sin(t * .001 * s.v + s.p) + 1) * .2})`
    sctx.arc(x, s.y * h, s.s * (s.z + .45), 0, 6.283); sctx.fill()
  }
}
function resize() {
  ratio = lite ? 1 : Math.min(devicePixelRatio || 1, 1.7)
  space.width = innerWidth * ratio; space.height = innerHeight * ratio
  space.style.width = innerWidth + 'px'; space.style.height = innerHeight + 'px'
  sctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  orb.resize(ratio); chart.resize(ratio); drawSpace(performance.now()); orb.draw(performance.now(), true)
}
function loop(t) {
  frame = requestAnimationFrame(loop)
  if (document.hidden || (still && t - lastDraw < 1000)) return
  if (lite && t - lastDraw < 50) return          // ~20 images/s en mode léger
  lastDraw = t; if (!lite) drawSpace(t); orb.draw(t, still)
}

// ---------- état visuel ----------
function applyState() {
  const ready = st.setups.filter((x) => !x.blocked)
  const s = st.kill.engaged ? 'stop' : !st.online ? 'offline' : ready.length ? 'setup' : 'idle'
  app.dataset.state = s; orb.setState(s)
  const lbl = { idle: 'VEILLE', setup: 'CONFIGURATION DÉTECTÉE', stop: 'STOP ENGAGÉ', offline: 'HORS LIGNE' }[s]
  $('#orb-state').textContent = lbl
  $('#orb-caption').textContent = {
    idle: 'AUCUNE CONFIGURATION · LE BOT OBSERVE', setup: `${ready.length} CONFIGURATION(S) · À TOI DE DÉCIDER`,
    stop: 'TOUT EST À L’ARRÊT · AGENTS COUPÉS', offline: 'API INJOIGNABLE · VÉRIFIE LES FENÊTRES',
  }[s]
  $('#scan-pill').textContent = s === 'setup' ? 'DÉTECTION' : s === 'stop' ? 'COUPÉ' : 'VEILLE'
}
let toastTimer
function toast(m) { const t = $('#toast'); t.textContent = m; t.classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('visible'), 2600) }

// ---------- données ----------
async function pollMarket() {
  try {
    const m = await get('/api/market')
    st.online = true; st.price = m.bid ?? null; st.market = m
    $('#bid').textContent = fmt(m.bid); $('#ask').textContent = fmt(m.ask)
    $('#spread').textContent = m.bid && m.ask ? fmt(m.ask - m.bid) : '—'
    $('#orb-price').textContent = fmt(m.bid); $('#symbol-label').textContent = m.symbol || 'GOLD'
    // L'heure des ticks est celle du serveur MT5 (pas UTC) : on mesure donc depuis quand le dernier tick a CHANGÉ.
    if (m.timestamp !== st.lastTs) { st.lastTs = m.timestamp; st.lastChange = Date.now() }
    const age = st.lastChange ? (Date.now() - st.lastChange) / 1000 : null
    const now = new Date(), wd = now.getUTCDay(), h = now.getUTCHours()
    const closed = wd === 6 || (wd === 5 && h >= 21) || (wd === 0 && h < 22)
    const cut = !closed && age != null && age > 90
    $('#tick-age').textContent = age == null ? '—' : age < 5 ? 'LIVE' : `${Math.round(age)} S`
    $('#feed-label').textContent = closed ? 'MARCHÉ FERMÉ' : cut ? 'FLUX COUPÉ' : 'FLUX EN DIRECT'
    $('#feed-dot').classList.toggle('stale', closed || cut)
    const banner = $('#feed-alert')
    banner.hidden = !cut
    if (cut) banner.innerHTML = `<b>⚠ FLUX COUPÉ</b> Aucun nouveau prix depuis ${Math.round(age / 60)} min : le prix affiché est figé.
      Vérifie que MT5 est ouvert et connecté (barres vertes en bas à droite) et que la fenêtre <b>4-MT5</b> tourne.`
    chart.set({ price: st.price }); renderTicket()
  } catch { st.online = false; $('#feed-label').textContent = 'API HORS LIGNE'; $('#feed-dot').classList.add('stale') }
  applyState()
}
async function pollKill() {
  try {
    st.kill = await get('/api/kill')
    $('#stop-label').textContent = st.kill.engaged ? 'STOP ENGAGÉ' : 'STOP'
    $('#stop-sub').textContent = st.kill.engaged ? (st.kill.reason || '').toUpperCase().slice(0, 48) : "FREIN D'URGENCE · 1 TAP"
    $('#stop-btn').disabled = st.kill.engaged
    $('#release-btn').hidden = !st.kill.engaged
  } catch { /* hors ligne : géré par pollMarket */ }
  applyState()
}
async function pollBars() { try { chart.set({ bars: await get(`/api/bars?tf=${tf}&limit=${tf === 60 ? 90 : 72}`) }) } catch {} }
async function pollScan() {
  try {
    const r = await get('/api/scan')
    st.setups = st.kill.engaged ? [] : r.setups
    chart.set({ setups: st.setups.filter((s) => s.tf === tf) })
    $('#scan-note').textContent = st.setups.some((x) => x.validated)
      ? 'Fenêtre nuit testée sur 12 ans de données FxPro : avantage modeste, aucune garantie. C’est toi qui décides.'
      : 'Calcul non validé par backtest. Information seulement : c’est toi qui décides dans MT5.'
    $('#scan-body').innerHTML = st.setups.length ? st.setups.map((s, i) => `
      <div class="setup ${s.side === 'BUY' ? 'buy' : 'sell'}">
        <div class="setup-head"><b>${s.side === 'BUY' ? 'ACHAT' : 'VENTE'}</b><span>${s.kind} · ${s.tf === 60 ? 'M1' : 'M5'}</span><em>${s.validated ? 'VALIDÉE 12 ANS' : `${s.sources}/${s.out_of} CONCORDENT`}</em></div>
        <div class="lv"><span>ENTRÉE</span><b>${fmt(s.entry)}</b></div>
        <div class="lv sl"><span>SL</span><b>${fmt(s.sl)}</b></div>
        <div class="lv tp1"><span>TP1</span><b>${fmt(s.tp1)}</b></div>
        <div class="lv tp2"><span>TP2</span><b>${fmt(s.tp2)}</b></div>
        ${s.exit_at ? `<p class="setup-note">Sortie du reste : ${new Date(s.exit_at).toLocaleString('fr-FR', { weekday: 'short', hour: '2-digit', minute: '2-digit' })} (fermeture automatique en papier) · ${s.lots} lot</p>` : ''}
        ${s.blocked ? `<p class="setup-block">⏸ ${s.blocked}</p>` : `<button class="take-btn" data-take="${i}">PRENDRE EN PAPIER</button>`}
      </div>`).join('') : '<p class="empty">Aucune configuration détectée.</p>'
  } catch {}
  applyState()
}
async function pollPositions() {
  try {
    const r = await get('/api/positions')
    const items = r.items || []
    $('#pos-count').textContent = items.length
    chart.set({ positions: items })
    $('#positions').innerHTML = items.length ? items.map((p) => `
      <div class="pos ${p.side === 'BUY' ? 'buy' : 'sell'}">
        <div class="pos-head"><b>${p.side === 'BUY' ? 'ACHAT' : 'VENTE'} ${p.volume}</b><span class="${p.profit >= 0 ? 'up' : 'down'}">${p.profit >= 0 ? '+' : ''}${fmt(p.profit)}</span></div>
        <div class="pos-lv"><span>ENTRÉE <b>${fmt(p.entry)}</b></span><span class="sl">SL <b>${fmt(p.sl)}</b></span><span class="tp1">TP1 <b>${fmt(p.tp1)}</b></span><span class="tp2">TP2 <b>${fmt(p.tp2)}</b></span></div>
      </div>`).join('') : '<p class="empty">Aucune position ouverte.<br><small>Ouvre une position dans MT5 : elle apparaît ici et sur le graphique.</small></p>'
  } catch {}
}

// ---------- trading papier : un tap = un ordre ----------
const ticket = { lots: 0.01, dist: 5, r1: 1, r2: 2 }
const STEP = { lots: .01, dist: .5, r1: .25, r2: .25 }
function renderTicket() {
  $('#t-lots').textContent = ticket.lots.toFixed(2); $('#t-dist').textContent = ticket.dist.toFixed(2)
  $('#t-r1').textContent = ticket.r1.toFixed(2) + ' R'; $('#t-r2').textContent = ticket.r2.toFixed(2) + ' R'
  const risk = ticket.dist * ticket.lots * 100
  $('#t-risk').textContent = fmt(risk) + ' $'
  $('#t-gain').textContent = fmt(risk * (ticket.r1 + ticket.r2) / 2) + ' $'
  const m = st.book || st.market || {}
  $('#oc-bid').textContent = fmt(m.bid); $('#oc-ask').textContent = fmt(m.ask)
  document.querySelectorAll('.oc').forEach((b) => { b.disabled = m.bid == null || st.kill.engaged || b.classList.contains('busy') })
}
document.querySelectorAll('.stepper').forEach((row) => row.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
  const k = row.dataset.k, d = Number(b.dataset.d)
  const lim = { lots: [.01, 1], dist: [.5, 100], r1: [.25, 10], r2: [.5, 20] }[k]
  ticket[k] = Math.round(Math.min(lim[1], Math.max(lim[0], ticket[k] + d * STEP[k])) * 100) / 100
  if (ticket.r2 < ticket.r1) ticket.r2 = ticket.r1
  renderTicket()
})))
async function openPaper(body, btn) {
  btn?.classList.add('busy'); renderTicket()
  try { await post('/api/paper/open', body); toast(`${body.side === 'BUY' ? 'ACHAT' : 'VENTE'} papier ouvert`); navigator.vibrate?.(30) }
  catch (e) { toast('Refusé : ' + e.message) }
  finally { btn?.classList.remove('busy'); pollPaper(); renderTicket() }
}
document.querySelectorAll('.oc').forEach((b) => b.addEventListener('click', () =>
  openPaper({ side: b.dataset.side, lots: ticket.lots, sl_dist: ticket.dist, r1: ticket.r1, r2: ticket.r2 }, b)))
$('#close-all').addEventListener('click', async () => {
  try { await post('/api/paper/close_all', {}); toast('Toutes les positions papier fermées'); navigator.vibrate?.(60) }
  catch (e) { toast('Refusé : ' + e.message) }
  pollPaper()
})
$('#scan-body').addEventListener('click', (e) => {
  const b = e.target.closest('[data-take]'); if (!b) return
  const s = st.setups[Number(b.dataset.take)]; if (!s) return
  openPaper({ side: s.side, lots: s.lots ?? ticket.lots, sl: s.sl, tp1: s.tp1, tp2: s.tp2, exit_at: s.exit_at }, b)
})
$('#paper-positions').addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-act]'); if (!b) return
  b.disabled = true
  try {
    if (b.dataset.act === 'close') { await post('/api/paper/close', { id: b.dataset.id }); toast('Position papier fermée') }
    if (b.dataset.act === 'be') { await post('/api/paper/modify', { id: b.dataset.id, sl: Number(b.dataset.entry) }); toast('SL au point mort') }
  } catch (err) { toast('Refusé : ' + err.message) }
  pollPaper()
})
async function pollPaper() {
  try {
    const r = await get('/api/paper')
    const items = r.positions || []
    if (r.price?.bid != null) st.book = r.price
    $('#paper-equity').textContent = fmt(r.account?.equity) + ' $'
    chart.set({ paper: items }); $('#close-all').hidden = items.length < 1; renderTicket()
    $('#paper-positions').innerHTML = items.length ? items.map((p) => `
      <div class="pos paper ${p.side === 'BUY' ? 'buy' : 'sell'}">
        <div class="pos-head"><b>${p.side === 'BUY' ? 'ACHAT' : 'VENTE'} ${p.lots}${p.tp1_done ? ' · ½' : ''}</b><span class="${p.pnl >= 0 ? 'up' : 'down'}">${p.pnl >= 0 ? '+' : ''}${fmt(p.pnl)}</span></div>
        <div class="pos-lv"><span>ENTRÉE <b>${fmt(p.entry)}</b></span><span class="sl">SL <b>${fmt(p.sl)}</b></span><span class="tp1">TP1 <b>${p.tp1_done ? '✓' : fmt(p.tp1)}</b></span><span class="tp2">TP2 <b>${fmt(p.tp2)}</b></span></div>
        ${p.exit_at ? `<div class="pos-exit">⏱ Fermeture automatique ${new Date(p.exit_at).toLocaleString('fr-FR', { weekday: 'short', hour: '2-digit', minute: '2-digit' })}</div>` : ''}
        <div class="pos-actions"><button data-act="be" data-id="${p.id}" data-entry="${p.entry}" ${p.sl === p.entry ? 'disabled' : ''}>SL → POINT MORT</button><button data-act="close" data-id="${p.id}" class="danger">FERMER</button></div>
      </div>`).join('') : '<p class="empty">Aucune position papier.<br><small>Utilise le ticket « Ordre papier » pour en ouvrir une.</small></p>'
  } catch {}
}

// ---------- baromètre ----------
function gaugeSVG(score) {
  const a = Math.PI * (1 - (score + 100) / 200)          // -100 → gauche, +100 → droite
  const x = 100 + 78 * Math.cos(a), y = 100 - 78 * Math.sin(a)
  const arc = (from, to, col) => {
    const p = (v) => { const t = Math.PI * (1 - (v + 100) / 200); return [100 + 88 * Math.cos(t), 100 - 88 * Math.sin(t)] }
    const [x1, y1] = p(from), [x2, y2] = p(to)
    return `<path d="M${x1.toFixed(1)} ${y1.toFixed(1)} A88 88 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}" stroke="${col}" stroke-width="10" fill="none" />`
  }
  return `<svg viewBox="0 0 200 112" class="gauge" aria-hidden="true">
    ${arc(-100, -50, '#ff4d5e')}${arc(-50, -15, '#b8414d')}${arc(-15, 15, '#4a6a6a')}${arc(15, 50, '#1f9e72')}${arc(50, 100, '#2ee59d')}
    <line x1="100" y1="100" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#ffce4d" stroke-width="3" stroke-linecap="round" />
    <circle cx="100" cy="100" r="6" fill="#ffce4d" />
  </svg>`
}
const VOTE = { 1: ['▲', 'up'], '-1': ['▼', 'down'], 0: ['●', 'flat'] }
async function pollGauge() {
  try {
    const r = await get('/api/gauge')
    $('#baro-note').textContent = r.note || ''
    $('#baro').innerHTML = r.horizons.map((h) => {
      if (!h.ready) return `<div class="baro"><div class="baro-head"><b>${h.label}</b><span>${h.tf}</span></div>
        <p class="empty">Historique insuffisant${h.bars != null ? ` (${h.bars} bougies)` : ''}. Il se charge depuis MT5 au démarrage du pont.</p></div>`
      const cls = h.score >= 15 ? 'buy' : h.score <= -15 ? 'sell' : 'flat'
      const chance = h.prob_up == null ? 'Pas assez d’historique pour estimer les chances.' :
        `Dans <b>${h.sample}</b> situations passées comparables, ${h.ahead_label} plus tard le prix était <span class="up">plus haut ${h.prob_up} %</span> · <span class="down">plus bas ${h.prob_down} %</span> du temps.${h.reliable ? '' : ' <em>(échantillon faible)</em>'}`
      return `<div class="baro ${cls}">
        <div class="baro-head"><b>${h.label}</b><span>${h.tf} · horizon ${h.ahead_label}</span></div>
        ${gaugeSVG(h.score)}
        <div class="baro-verdict"><strong>${h.verdict}</strong><span>score ${h.score > 0 ? '+' : ''}${h.score}</span></div>
        <p class="baro-chance">${chance}</p>
        <div class="votes">${h.votes.map((v) => `<span class="vote ${VOTE[v.vote][1]}">${VOTE[v.vote][0]} ${v.name}</span>`).join('')}</div>
      </div>`
    }).join('')
  } catch { $('#baro').innerHTML = '<p class="empty">Baromètre indisponible (données en cours de chargement).</p>' }
}

// ---------- commandes ----------
$('#stop-btn').addEventListener('click', async () => {
  navigator.vibrate?.(80)
  try { await post('/api/kill', { engaged: true, reason: 'STOP manuel depuis le flight deck' }); toast('STOP ENGAGÉ — tout est à l’arrêt') }
  catch (e) { toast('Échec du STOP : ' + e.message) }
  pollKill(); pollScan(); pollPaper()
})
$('#release-btn').addEventListener('click', async () => {
  const token = prompt('Mot de passe administrateur pour relâcher le frein :')
  if (!token) return
  try { await post('/api/kill', { engaged: false }, token); toast('Frein relâché — reprise') }
  catch { toast('Mot de passe refusé') }
  pollKill()
})
document.querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => {
  document.querySelectorAll('.seg button').forEach((x) => x.classList.toggle('on', x === b))
  tf = Number(b.dataset.tf); $('#bar-clock').textContent = tf === 60 ? 'M1' : 'M5'; pollBars(); pollScan()
}))
$('#motion-toggle').addEventListener('click', (e) => {
  still = !still; e.currentTarget.setAttribute('aria-pressed', String(still)); e.currentTarget.classList.toggle('is-muted', still)
  toast(still ? 'Animations réduites' : 'Animations activées')
})

addEventListener('resize', resize, { passive: true })
resize(); frame = requestAnimationFrame(loop)
if (still) $('#motion-toggle').classList.add('is-muted')
// Rafraîchissement séquentiel : une requête attend la fin de la précédente, rien ne s'empile.
function every(fn, ms) { const run = async () => { try { await fn() } finally { setTimeout(run, document.hidden ? ms * 4 : ms) } }; run() }
every(pollMarket, 1000); every(pollPaper, 1000); every(pollKill, 2000); every(pollPositions, 1500)
// Fenêtre nuit : seul effet qui a tenu nos tests (2016-2018 + 2026), après spread et swap.
// Entrée 20:50 UTC lundi, mardi, jeudi (mercredi = swap x3, vendredi = week-end) ; sortie 07:00 UTC le lendemain.
function nightWindow(now = new Date()) {
  const ENTRY_DAYS = [1, 2, 4]
  const at = (d, h, m) => new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), h, m))
  for (let k = -1; k <= 7; k++) {
    const day = new Date(now.getTime() + k * 864e5)
    if (!ENTRY_DAYS.includes(day.getUTCDay())) continue
    const start = at(day, 20, 50), end = new Date(at(day, 7, 0).getTime() + 864e5)
    if (now >= start && now < end) return { open: true, start, end }
    if (now < start) return { open: false, start, end }
  }
  return { open: false }
}
let renderNight = function () {
  const el = document.getElementById('night'); if (!el) return
  const w = nightWindow(), hm = d => d.toLocaleString('fr-FR', { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  el.className = 'night ' + (w.open ? 'on' : 'off')
  el.innerHTML = w.open
    ? `<b>FENÊTRE NUIT · OUVERTE</b><span>Achat possible maintenant (papier) · sortie ${hm(w.end)}</span><small>Léger avantage historique, pas une garantie. C'est toi qui décides.</small>`
    : `<b>FENÊTRE NUIT · FERMÉE</b><span>Prochaine ouverture ${w.start ? hm(w.start) : '—'} → sortie ${w.end ? hm(w.end) : '—'}</span><small>Lun, mar, jeu seulement (mercredi : swap ×3).</small>`
}
let nightPlan = null
async function pollNight() { try { nightPlan = await get('/api/night') } catch { nightPlan = null } renderNight() }
const _renderNight = renderNight
renderNight = function () {
  _renderNight()
  const el = document.getElementById('night'); if (!el || !nightPlan?.ready) return
  const p = nightPlan
  el.insertAdjacentHTML('beforeend', `<div class="night-plan">
    <span>ENTRÉE <b>${fmt(p.entry)}</b></span><span class="sl">SL <b>${fmt(p.sl)}</b></span>
    <span class="tp1">TP1 <b>${fmt(p.tp1)}</b> <small>50 % puis point mort</small></span><span class="tp2">TP2 <b>${fmt(p.tp2)}</b></span>
    <span>LOTS <b>${p.lots}</b> <small>≈ ${fmt(p.risk_usd)} $ risqués (${p.risk_pct} % de ${p.capital.toLocaleString('fr-FR')} $)</small></span>
    <span class="${p.spread_ok ? '' : 'bad'}">SPREAD <b>${fmt(p.spread)}</b> <small>max conseillé ${fmt(p.max_spread)}</small></span>
  </div><small>${p.stats}</small>`)
}
renderNight(); setInterval(renderNight, 30000); every(pollNight, 15000)

every(pollBars, 5000); every(pollScan, 5000); every(pollGauge, 15000)

// ---------- journal de bord (overlay) ----------
const jr = (n) => `<span class="${n > 0 ? 'up' : n < 0 ? 'down' : ''}">${n > 0 ? '+' : ''}${fmt(n)} $</span>`
async function loadJournal(day) {
  try {
    const j = await get('/api/journal' + (day ? `?day=${day}` : ''))
    const sel = $('#journal-day')
    sel.innerHTML = (j.days.length ? j.days : ['—']).map((d) => `<option ${d === j.day ? 'selected' : ''}>${d}</option>`).join('')
    const s = j.summary, n = j.night
    $('#journal-body').innerHTML = `
      <div class="jr-cards">
        <div><small>TRADES DU JOUR</small><b>${s.trades}</b><em>${s.wins} gagnants · ${s.losses} perdants</em></div>
        <div><small>RÉSULTAT DU JOUR</small><b>${jr(s.pnl)}</b><em>PF ${s.pf ?? '—'}</em></div>
        <div class="night-card"><small>FENÊTRE NUIT · DEPUIS LE DÉBUT</small><b>${n.trades} nuit(s) · ${jr(n.pnl)}</b>
          <em>PF réel ${n.pf ?? '—'} · backtest ${n.backtest_pf}</em><em>${n.note}</em></div>
      </div>
      ${j.trades.length ? `<table class="jr-table"><thead><tr><th>Fermé</th><th>Stratégie</th><th>Sens</th><th>Lots</th><th>Entrée</th><th>Sortie</th><th>Raison</th><th>Résultat</th></tr></thead><tbody>
        ${j.trades.map((t) => `<tr><td>${t.closed_at.slice(11, 16)}</td><td>${t.strategy}</td><td>${t.side === 'BUY' ? 'ACHAT' : 'VENTE'}</td><td>${t.lots}</td>
          <td>${fmt(t.entry)}</td><td>${fmt(t.exit)}</td><td>${t.reason}</td><td>${jr(t.pnl)}</td></tr>`).join('')}
      </tbody></table>` : '<p class="empty">Aucun trade fermé ce jour-là.</p>'}`
  } catch { $('#journal-body').innerHTML = '<p class="empty">Journal indisponible.</p>' }
}
$('#journal-btn').addEventListener('click', () => { $('#journal').hidden = false; loadJournal() })
$('#journal-close').addEventListener('click', () => { $('#journal').hidden = true })
$('#journal').addEventListener('click', (e) => { if (e.target.id === 'journal') $('#journal').hidden = true })
$('#journal-day').addEventListener('change', (e) => loadJournal(e.target.value))
