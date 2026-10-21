// Graphique bougies + niveaux : positions MT5 (entrée pleine, SL / TP1 / TP2 en pointillés) et configurations du scan.
import { C, rgba } from './palette.js'

export function createChart(canvas) {
  const ctx = canvas.getContext('2d')
  let data = { bars: [], positions: [], setups: [], price: null }

  function resize(ratio) {
    const w = canvas.clientWidth, h = canvas.clientHeight
    canvas.width = Math.round(w * ratio); canvas.height = Math.round(h * ratio)
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0); draw()
  }

  function draw() {
    const w = canvas.clientWidth, h = canvas.clientHeight
    ctx.clearRect(0, 0, w, h)
    const { bars, positions, setups, price } = data
    const axis = 70, top = 14, bottom = h - 14
    if (!bars.length) {
      ctx.fillStyle = rgba(C.grey, .8); ctx.font = '12px "Space Mono", monospace'; ctx.textAlign = 'center'
      ctx.fillText('EN ATTENTE DES PREMIÈRES BOUGIES…', w / 2, h / 2); return
    }
    const levels = []
    positions.forEach((p) => levels.push(p.entry, p.sl, p.tp1, p.tp2))
    setups.forEach((s) => levels.push(s.entry, s.sl, s.tp1, s.tp2))
    const vals = bars.flatMap((b) => [b.high, b.low]).concat(levels.filter((v) => v != null), price ?? [])
    let hi = Math.max(...vals), lo = Math.min(...vals); const padv = (hi - lo) * .06 || 1; hi += padv; lo -= padv
    const y = (p) => top + (hi - p) / (hi - lo) * (bottom - top)
    const step = (w - axis) / bars.length

    // grille
    ctx.strokeStyle = rgba(C.teal, .06); ctx.lineWidth = 1
    for (let i = 0; i <= 5; i++) { const yy = top + i * (bottom - top) / 5; ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(w - axis, yy); ctx.stroke() }

    // bougies
    bars.forEach((b, i) => {
      const x = i * step + step / 2, up = b.close >= b.open, col = up ? C.green : C.red
      ctx.strokeStyle = rgba(col, .95); ctx.fillStyle = rgba(col, .9); ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(x, y(b.high)); ctx.lineTo(x, y(b.low)); ctx.stroke()
      const bw = Math.max(1.5, step * .62), yt = y(Math.max(b.open, b.close)), bh = Math.max(1, Math.abs(y(b.open) - y(b.close)))
      ctx.fillRect(x - bw / 2, yt, bw, bh)
    })

    const tags = []
    const line = (v, col, dash, label, width = 1.3) => {
      if (v == null) return
      const yy = y(v)
      ctx.save(); ctx.setLineDash(dash); ctx.strokeStyle = rgba(col, .95); ctx.lineWidth = width
      ctx.shadowColor = rgba(col, .8); ctx.shadowBlur = 6
      ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(w - axis, yy); ctx.stroke(); ctx.restore()
      tags.push({ yy, col, label, v })
    }
    // étiquettes sans chevauchement : on les écarte d'au moins 14 px
    const placeTags = () => {
      tags.sort((a, b) => a.yy - b.yy)
      let last = -Infinity
      for (const t of tags) { t.ty = Math.max(t.yy, last + 14); last = t.ty }
      ctx.font = '10px "Space Mono", monospace'
      for (const t of tags) {
        ctx.fillStyle = rgba(t.col, .18); ctx.fillRect(w - axis + 2, t.ty - 9, axis - 4, 16)
        ctx.fillStyle = rgba(t.col, 1); ctx.textAlign = 'right'; ctx.fillText(t.v.toFixed(2), w - 6, t.ty + 3)
        ctx.textAlign = 'left'; ctx.fillText(t.label, 6, t.ty - 3)
      }
    }
    setups.forEach((s) => {
      line(s.entry, C.teal, [2, 4], `CONFIG ${s.side === 'BUY' ? 'ACHAT' : 'VENTE'} ${s.kind}`)
      line(s.sl, C.teal, [2, 4], 'SL'); line(s.tp1, C.teal, [2, 4], 'TP1'); line(s.tp2, C.teal, [2, 4], 'TP2')
    })
    positions.forEach((p) => {
      line(p.entry, p.side === 'BUY' ? C.green : C.red, [], `POSITION ${p.side === 'BUY' ? 'ACHAT' : 'VENTE'} ${p.volume}`, 1.6)
      line(p.sl, C.red, [6, 5], 'SL'); line(p.tp1, C.green, [6, 5], 'TP1'); line(p.tp2, C.gold, [6, 5], 'TP2')
    })
    if (price != null) line(price, C.gold, [1, 3], 'PRIX', 1)
    placeTags()

    // axe
    ctx.strokeStyle = rgba(C.teal, .25); ctx.beginPath(); ctx.moveTo(w - axis, 0); ctx.lineTo(w - axis, h); ctx.stroke()
    ctx.fillStyle = rgba(C.grey, .9); ctx.font = '10px "Space Mono", monospace'; ctx.textAlign = 'right'
    ctx.fillText(hi.toFixed(2), w - 6, top + 4); ctx.fillText(lo.toFixed(2), w - 6, bottom)
  }

  return { resize, draw, set: (d) => { data = { ...data, ...d }; draw() } }
}
