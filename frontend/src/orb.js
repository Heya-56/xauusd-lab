// Noyau holographique (adapté du prototype ULTRON de l'Académie) : sa couleur traduit l'état du bot.
import { STATE_COLOR, rgba } from './palette.js'

export function createOrb(canvas) {
  const ctx = canvas.getContext('2d', { alpha: true })
  const pointer = { down: false, lastX: 0, lastY: 0, spinX: 0, spinY: 0 }
  let state = 'idle', mix = STATE_COLOR.idle.slice(), pulse = 0

  canvas.addEventListener('pointerdown', (e) => { pointer.down = true; pointer.lastX = e.clientX; pointer.lastY = e.clientY; canvas.setPointerCapture?.(e.pointerId) })
  canvas.addEventListener('pointermove', (e) => {
    if (!pointer.down) return
    pointer.spinY += (e.clientX - pointer.lastX) * .006; pointer.spinX += (e.clientY - pointer.lastY) * .006
    pointer.lastX = e.clientX; pointer.lastY = e.clientY
  })
  ;['pointerup', 'pointercancel', 'lostpointercapture'].forEach((n) => canvas.addEventListener(n, () => { pointer.down = false }))

  function resize(ratio) {
    const r = canvas.parentElement.getBoundingClientRect()
    canvas.width = Math.round(r.width * ratio); canvas.height = Math.round(r.height * ratio)
    canvas.style.width = r.width + 'px'; canvas.style.height = r.height + 'px'
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  }

  function draw(time, still) {
    const target = STATE_COLOR[state]
    for (let i = 0; i < 3; i++) mix[i] += (target[i] - mix[i]) * .06   // transition douce entre états
    const c = mix.map(Math.round)
    const w = canvas.clientWidth, h = canvas.clientHeight
    ctx.clearRect(0, 0, w, h)
    const cx = w * .5, cy = h * .49
    const speed = state === 'setup' ? 2.2 : state === 'stop' ? .25 : 1
    pulse = state === 'stop' ? (Math.sin(time * .006) + 1) / 2 : state === 'setup' ? (Math.sin(time * .004) + 1) / 2 : 0
    const radius = Math.min(w, h) * (.305 + pulse * .012)
    const rotation = (still ? 0 : time * .00022 * speed) + pointer.spinY
    const tilt = .35 + pointer.spinX * .3

    const aura = ctx.createRadialGradient(cx, cy, radius * .25, cx, cy, radius * 1.75)
    aura.addColorStop(0, rgba(c, .2 + pulse * .12)); aura.addColorStop(.45, rgba(c, .08)); aura.addColorStop(1, rgba(c, 0))
    ctx.fillStyle = aura; ctx.fillRect(0, 0, w, h)
    ctx.save(); ctx.translate(cx, cy)
    for (let i = 0; i < 3; i++) {
      ctx.save(); ctx.rotate(rotation * (i % 2 ? -.55 : .7) + i * 1.1); ctx.scale(1, .24 + i * .12)
      ctx.beginPath(); ctx.ellipse(0, 0, radius * (1.45 + i * .18), radius * (1.45 + i * .18), 0, 0, Math.PI * 2)
      ctx.strokeStyle = rgba(c, [.58, .36, .25][i]); ctx.lineWidth = i === 0 ? 1.5 : 1
      ctx.setLineDash(i === 1 ? [5, 9] : []); ctx.stroke(); ctx.restore()
    }
    ctx.setLineDash([])
    const sphere = ctx.createRadialGradient(-radius * .35, -radius * .4, radius * .04, radius * .15, radius * .12, radius * 1.2)
    sphere.addColorStop(0, rgba(c, .32)); sphere.addColorStop(.28, rgba(c, .14)); sphere.addColorStop(.72, 'rgba(2,30,40,.35)'); sphere.addColorStop(1, 'rgba(0,10,14,.8)')
    ctx.beginPath(); ctx.arc(0, 0, radius, 0, Math.PI * 2); ctx.fillStyle = sphere; ctx.fill()
    ctx.save(); ctx.beginPath(); ctx.arc(0, 0, radius, 0, Math.PI * 2); ctx.clip()
    for (let i = 0; i < 13; i++) {
      const a = rotation + i * Math.PI / 13, sq = Math.abs(Math.cos(a))
      ctx.beginPath(); ctx.ellipse(0, 0, Math.max(2, radius * sq), radius, a * .16 + tilt * .12, 0, Math.PI * 2)
      ctx.strokeStyle = rgba(c, .08 + sq * .35); ctx.lineWidth = .7 + sq * .5; ctx.stroke()
    }
    for (let i = 1; i < 9; i++) {
      const y = -radius + radius * 2 * i / 9, span = Math.sqrt(Math.max(0, radius * radius - y * y))
      ctx.beginPath(); ctx.ellipse(0, y * .88, span, Math.max(1, radius * .1), 0, 0, Math.PI * 2)
      ctx.strokeStyle = rgba(c, .19); ctx.lineWidth = .6; ctx.stroke()
    }
    for (let i = 0; i < 48; i++) {
      const a = i * 2.399 + rotation * .6, rr = radius * (.12 + ((i * 37) % 83) / 100)
      ctx.beginPath(); ctx.arc(Math.cos(a) * rr, Math.sin(a * 1.23) * rr, i % 6 === 0 ? 1.8 : .8, 0, Math.PI * 2)
      ctx.fillStyle = i % 4 === 0 ? 'rgba(235,255,250,.95)' : rgba(c, .7); ctx.fill()
    }
    ctx.restore()
    ctx.beginPath(); ctx.arc(0, 0, radius, -1.9 + rotation * .3, -.4 + rotation * .3)
    ctx.strokeStyle = rgba([235, 255, 250], .95); ctx.lineWidth = 2.5; ctx.shadowBlur = 20; ctx.shadowColor = rgba(c, 1); ctx.stroke(); ctx.shadowBlur = 0
    ctx.beginPath(); ctx.arc(0, 0, radius * 1.06, .2 - rotation, 1.4 - rotation)
    ctx.strokeStyle = rgba(c, .7); ctx.lineWidth = 1.2; ctx.stroke()
    ctx.restore()
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(-rotation * .3)
    for (let i = 0; i < 72; i++) {
      const a = i * Math.PI * 2 / 72, inner = radius * 1.2, outer = inner + (i % 6 === 0 ? 9 : 3)
      ctx.beginPath(); ctx.moveTo(Math.cos(a) * inner, Math.sin(a) * inner); ctx.lineTo(Math.cos(a) * outer, Math.sin(a) * outer)
      ctx.strokeStyle = i % 6 === 0 ? rgba(c, .8) : rgba(c, .28); ctx.lineWidth = i % 6 === 0 ? 1.2 : .6; ctx.stroke()
    }
    ctx.restore()
  }

  return { resize, draw, setState: (s) => { state = s } }
}
