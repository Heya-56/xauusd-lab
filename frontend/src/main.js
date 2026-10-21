import './ultron.scss'
import { get, post } from './api.js'
import { createOrb } from './orb.js'
import { createChart } from './chart.js'

const $ = (s) => document.querySelector(s)
const app = $('#app')
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
let still = reduced, frame = 0, ratio = 1, tf = 300
const space = $('#space-canvas'), sctx = space.getContext('2d')
const orb = createOrb($('#orb-canvas'))
const chart = createChart($('#chart'))
const st = { kill: { engaged: false }, setups: [], online: false, price: null }
const fmt = (n, d = 2) => (n == null || Number.isNaN(n) ? '—' : Number(n).toFixed(d))

// ---------- fond étoilé ----------
const stars = Array.from({ length: 160 }, () => ({ x: Math.random(), y: Math.random(), z: Math.random(), s: Math.random() * 1.4 + .2, p: Math.random() * 6.28, v: Math.random() * .8 + .2 }))
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
  ratio = Math.min(devicePixelRatio || 1, 1.7)
  space.width = innerWidth * ratio; space.height = innerHeight * ratio
  space.style.width = innerWidth + 'px'; space.style.height = innerHeight + 'px'
  sctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  orb.resize(ratio); chart.resize(ratio); drawSpace(performance.now()); orb.draw(performance.now(), true)
}
function loop(t) { frame = requestAnimationFrame(loop); drawSpace(t); orb.draw(t, still) }

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
    st.online = true; st.price = m.bid ?? null
    $('#bid').textContent = fmt(m.bid); $('#ask').textContent = fmt(m.ask)
    $('#spread').textContent = m.bid && m.ask ? fmt(m.ask - m.bid) : '—'
    $('#orb-price').textContent = fmt(m.bid); $('#symbol-label').textContent = m.symbol || 'GOLD'
    const age = m.timestamp ? (Date.now() - Date.parse(m.timestamp)) / 1000 : null
    $('#tick-age').textContent = age == null ? '—' : age < 5 ? 'LIVE' : `${Math.round(age)} S`
    $('#feed-label').textContent = age != null && age < 30 ? 'FLUX EN DIRECT' : 'FLUX EN PAUSE'
    $('#feed-dot').classList.toggle('stale', !(age != null && age < 30))
    chart.set({ price: st.price })
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
    $('#scan-body').innerHTML = st.setups.length ? st.setups.map((s) => `
      <div class="setup ${s.side === 'BUY' ? 'buy' : 'sell'}">
        <div class="setup-head"><b>${s.side === 'BUY' ? 'ACHAT' : 'VENTE'}</b><span>${s.kind} · ${s.tf === 60 ? 'M1' : 'M5'}</span><em>${s.sources}/${s.out_of} CONCORDENT</em></div>
        <div class="lv"><span>ENTRÉE</span><b>${fmt(s.entry)}</b></div>
        <div class="lv sl"><span>SL</span><b>${fmt(s.sl)}</b></div>
        <div class="lv tp1"><span>TP1</span><b>${fmt(s.tp1)}</b></div>
        <div class="lv tp2"><span>TP2</span><b>${fmt(s.tp2)}</b></div>
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

// ---------- commandes ----------
$('#stop-btn').addEventListener('click', async () => {
  navigator.vibrate?.(80)
  try { await post('/api/kill', { engaged: true, reason: 'STOP manuel depuis le flight deck' }); toast('STOP ENGAGÉ — tout est à l’arrêt') }
  catch (e) { toast('Échec du STOP : ' + e.message) }
  pollKill(); pollScan()
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
pollMarket(); pollKill(); pollBars(); pollScan(); pollPositions()
setInterval(pollMarket, 1000); setInterval(pollKill, 2000); setInterval(pollPositions, 1500)
setInterval(pollBars, 5000); setInterval(pollScan, 5000)
