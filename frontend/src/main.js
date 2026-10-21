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
  const s = st.kill.engaged ? 'stop' : !st.online ? 'offline' : st.setups.length ? 'setup' : 'idle'
  app.dataset.state = s; orb.setState(s)
  const lbl = { idle: 'VEILLE', setup: 'CONFIGURATION DÉTECTÉE', stop: 'STOP ENGAGÉ', offline: 'HORS LIGNE' }[s]
  $('#orb-state').textContent = lbl
  $('#orb-caption').textContent = {
    idle: 'AUCUNE CONFIGURATION · LE BOT OBSERVE', setup: `${st.setups.length} CONFIGURATION(S) · À TOI DE DÉCIDER`,
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
    const age = m.timestamp ? (Date.now() - Date.parse(m.timestamp)) / 1000 : null
    $('#tick-age').textContent = age == null ? '—' : age < 5 ? 'LIVE' : `${Math.round(age)} S`
    $('#feed-label').textContent = age != null && age < 30 ? 'FLUX EN DIRECT' : 'FLUX EN PAUSE'
    $('#feed-dot').classList.toggle('stale', !(age != null && age < 30))
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
    $('#scan-body').innerHTML = st.setups.length ? st.setups.map((s, i) => `
      <div class="setup ${s.side === 'BUY' ? 'buy' : 'sell'}">
        <div class="setup-head"><b>${s.side === 'BUY' ? 'ACHAT' : 'VENTE'}</b><span>${s.kind} · ${s.tf === 60 ? 'M1' : 'M5'}</span><em>${s.sources}/${s.out_of} CONCORDENT</em></div>
        <div class="lv"><span>ENTRÉE</span><b>${fmt(s.entry)}</b></div>
        <div class="lv sl"><span>SL</span><b>${fmt(s.sl)}</b></div>
        <div class="lv tp1"><span>TP1</span><b>${fmt(s.tp1)}</b></div>
        <div class="lv tp2"><span>TP2</span><b>${fmt(s.tp2)}</b></div>
        <button class="take-btn" data-take="${i}">PRENDRE EN PAPIER</button>
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

// ---------- trading papier ----------
const ticket = { side: 'BUY', lots: 0.01, dist: 5, r1: 1, r2: 2 }
const STEP = { lots: .01, dist: .5, r1: .25, r2: .25 }
function ticketLevels() {
  const m = st.book || st.market || {}, s = ticket.side === 'BUY' ? 1 : -1
  const entry = ticket.side === 'BUY' ? m.ask : m.bid
  if (entry == null) return null
  return { entry, sl: entry - s * ticket.dist, tp1: entry + s * ticket.dist * ticket.r1, tp2: entry + s * ticket.dist * ticket.r2 }
}
function renderTicket() {
  $('#t-lots').textContent = ticket.lots.toFixed(2); $('#t-dist').textContent = ticket.dist.toFixed(2)
  $('#t-r1').textContent = ticket.r1.toFixed(2) + ' R'; $('#t-r2').textContent = ticket.r2.toFixed(2) + ' R'
  const lv = ticketLevels()
  $('#t-sl').textContent = fmt(lv?.sl); $('#t-tp1').textContent = fmt(lv?.tp1); $('#t-tp2').textContent = fmt(lv?.tp2)
  $('#t-risk').textContent = lv ? fmt(ticket.dist * ticket.lots * 100) + ' $' : '—'
  const b = $('#open-btn'); b.className = 'open-btn ' + (ticket.side === 'BUY' ? 'buy' : 'sell')
  b.textContent = `OUVRIR ${ticket.side === 'BUY' ? 'ACHAT' : 'VENTE'} PAPIER · ${ticket.lots.toFixed(2)}`
  b.disabled = !lv || st.kill.engaged
  chart.set({ preview: lv ? { side: ticket.side, ...lv } : null })
}
document.querySelectorAll('.side-seg button').forEach((b) => b.addEventListener('click', () => {
  ticket.side = b.dataset.side
  document.querySelectorAll('.side-seg button').forEach((x) => { x.classList.toggle('on', x === b); x.setAttribute('aria-checked', String(x === b)) })
  renderTicket()
}))
document.querySelectorAll('.stepper').forEach((row) => row.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
  const k = row.dataset.k, d = Number(b.dataset.d)
  const lim = { lots: [.01, 1], dist: [.5, 100], r1: [.25, 10], r2: [.5, 20] }[k]
  ticket[k] = Math.round(Math.min(lim[1], Math.max(lim[0], ticket[k] + d * STEP[k])) * 100) / 100
  if (ticket.r2 < ticket.r1) ticket.r2 = ticket.r1
  renderTicket()
})))
async function openPaper(body) {
  try { await post('/api/paper/open', body); toast('Position papier ouverte'); navigator.vibrate?.(30); pollPaper() }
  catch (e) { toast('Refusé : ' + e.message) }
}
$('#open-btn').addEventListener('click', () => {
  const lv = ticketLevels(); if (!lv) return
  openPaper({ side: ticket.side, lots: ticket.lots, sl_dist: ticket.dist, r1: ticket.r1, r2: ticket.r2 })
})
$('#scan-body').addEventListener('click', (e) => {
  const b = e.target.closest('[data-take]'); if (!b) return
  const s = st.setups[Number(b.dataset.take)]; if (!s) return
  openPaper({ side: s.side, lots: ticket.lots, sl: s.sl, tp1: s.tp1, tp2: s.tp2 })
})
$('#paper-positions').addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-act]'); if (!b) return
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
    chart.set({ paper: items })
    $('#paper-positions').innerHTML = items.length ? items.map((p) => `
      <div class="pos paper ${p.side === 'BUY' ? 'buy' : 'sell'}">
        <div class="pos-head"><b>${p.side === 'BUY' ? 'ACHAT' : 'VENTE'} ${p.lots}${p.tp1_done ? ' · ½' : ''}</b><span class="${p.pnl >= 0 ? 'up' : 'down'}">${p.pnl >= 0 ? '+' : ''}${fmt(p.pnl)}</span></div>
        <div class="pos-lv"><span>ENTRÉE <b>${fmt(p.entry)}</b></span><span class="sl">SL <b>${fmt(p.sl)}</b></span><span class="tp1">TP1 <b>${p.tp1_done ? '✓' : fmt(p.tp1)}</b></span><span class="tp2">TP2 <b>${fmt(p.tp2)}</b></span></div>
        <div class="pos-actions"><button data-act="be" data-id="${p.id}" data-entry="${p.entry}" ${p.sl === p.entry ? 'disabled' : ''}>SL → POINT MORT</button><button data-act="close" data-id="${p.id}" class="danger">FERMER</button></div>
      </div>`).join('') : '<p class="empty">Aucune position papier.<br><small>Utilise le ticket « Ordre papier » pour en ouvrir une.</small></p>'
  } catch {}
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
every(pollBars, 5000); every(pollScan, 5000)
