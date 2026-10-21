import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  AnimatorGeneralProvider, Animator, Animated, Text,
  FrameCorners, FrameOctagon, GridLines, Dots,
} from '@arwes/react'
import { get, post, type Bar, type Consensus, type Kill, type Market, type Signal, type Status } from './api'

function usePoll<T>(path: string, ms: number): [T | null, string | null, () => void] {
  const [data, setData] = useState<T | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const load = useCallback(() => {
    get<T>(path).then(d => { setData(d); setErr(null) }).catch(e => setErr(String(e.message ?? e)))
  }, [path])
  useEffect(() => { load(); const id = setInterval(load, ms); return () => clearInterval(id) }, [load, ms])
  return [data, err, load]
}

function Panel({ title, children, tone = 'gold' }: { title: string; children: ReactNode; tone?: 'gold' | 'red' }) {
  return (
    <Animator>
      <section className={`panel tone-${tone}`}>
        <FrameCorners strokeWidth={2} cornerLength={14} />
        <div className="panel-body">
          <h2><Text>{title}</Text></h2>
          {children}
        </div>
      </section>
    </Animator>
  )
}

const fmt = (n?: number | null, d = 2) => (n === undefined || n === null || Number.isNaN(n) ? '—' : n.toFixed(d))
const ACTION_CLASS: Record<string, string> = { BUY: 'buy', SELL: 'sell', NONE: 'none' }
const LABEL: Record<string, string> = { LONG: 'ACHAT', SHORT: 'VENTE', NO_TRADE: 'NEUTRE' }

function Candles({ bars }: { bars: Bar[] }) {
  if (!bars.length) return <p className="muted">En attente des premières bougies…</p>
  const W = 720, H = 220, pad = 6, axis = 54
  const hi = Math.max(...bars.map(b => b.high)), lo = Math.min(...bars.map(b => b.low))
  const y = (p: number) => pad + (hi - p) / (hi - lo || 1) * (H - 2 * pad)
  const step = (W - axis) / bars.length
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Graphique en bougies">
      {bars.map((b, i) => {
        const up = b.close >= b.open, x = i * step + step / 2
        return (
          <g key={b.ts} className={up ? 'up' : 'down'}>
            <line x1={x} x2={x} y1={y(b.high)} y2={y(b.low)} />
            <rect x={x - step * 0.35} width={step * 0.7} y={y(Math.max(b.open, b.close))}
              height={Math.max(1, Math.abs(y(b.open) - y(b.close)))} />
          </g>
        )
      })}
      <line className="axis" x1={W - axis + 4} x2={W - axis + 4} y1={0} y2={H} />
      <text x={W - 2} y={12} textAnchor="end">{fmt(hi)}</text>
      <text x={W - 2} y={H - 4} textAnchor="end">{fmt(lo)}</text>
    </svg>
  )
}

function StopButton({ kill, refresh }: { kill: Kill | null; refresh: () => void }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const engaged = !!kill?.engaged
  const engage = async () => {
    setBusy(true)
    try { await post('/api/kill', { engaged: true, reason: 'STOP manuel depuis le tableau de bord' }); setMsg('') }
    catch (e) { setMsg(String(e)) } finally { setBusy(false); refresh() }
  }
  const release = async () => {
    const token = window.prompt('Jeton administrateur pour relâcher le frein :')
    if (!token) return
    setBusy(true)
    try { await post('/api/kill', { engaged: false }, token); setMsg('') }
    catch (e) { setMsg('Relâchement refusé : ' + String(e)) } finally { setBusy(false); refresh() }
  }
  return (
    <div className={`stop ${engaged ? 'engaged' : ''}`}>
      <button className="stop-btn" onClick={engage} disabled={busy || engaged} aria-label="Frein d'urgence : tout arrêter">
        <FrameOctagon squareSize={18} strokeWidth={3} />
        <span>{engaged ? 'STOP ENGAGÉ' : 'STOP'}</span>
      </button>
      <p className="stop-state">
        {engaged
          ? <>Agents à l'arrêt, position papier fermée, ordres bloqués.<br /><small>{kill?.reason} · {kill?.at?.slice(0, 19).replace('T', ' ')} UTC</small></>
          : 'Un clic coupe immédiatement tout le bot.'}
      </p>
      {engaged && <button className="release" onClick={release} disabled={busy}>Relâcher le frein (admin)</button>}
      {msg && <p className="error">{msg}</p>}
    </div>
  )
}

export function App() {
  const [tf, setTf] = useState<60 | 300>(300)
  const [kill, killErr, refreshKill] = usePoll<Kill>('/api/kill', 2000)
  const [market] = usePoll<Market>('/api/market', 1000)
  const [bars] = usePoll<Bar[]>(`/api/bars?tf=${tf}&limit=${tf === 60 ? 120 : 96}`, 5000)
  const [agents, agentsErr] = usePoll<Signal[]>('/api/agents', 5000)
  const [consensus] = usePoll<Consensus>('/api/consensus', 5000)
  const [status] = usePoll<Status>('/api/status', 5000)
  const spread = market?.bid && market?.ask ? market.ask - market.bid : undefined
  const online = !killErr

  return (
    <AnimatorGeneralProvider duration={{ enter: 0.4, exit: 0.3, stagger: 0.06 }}>
      <Animator active combine manager="stagger">
        <div className="bg"><GridLines lineColor="hsla(42, 70%, 55%, 0.07)" distance={40} /><Dots color="hsla(42, 70%, 55%, 0.12)" distance={40} /></div>
        <div className="app">
          <header>
            <Animator>
              <Animated as="div" className="brand" animated={['fade']}>
                <span className="logo">HINOVA <b>DIGITAL</b></span>
                <span className="sub">XAUUSD LAB · TERMINAL AGENTS</span>
              </Animated>
            </Animator>
            <div className="badges">
              <span className="badge paper">MODE PAPIER</span>
              <span className={`badge ${online ? 'ok' : 'ko'}`}>{online ? 'API CONNECTÉE' : 'API HORS LIGNE'}</span>
            </div>
          </header>

          <div className="grid">
            <Panel title="Frein d'urgence" tone="red"><StopButton kill={kill} refresh={refreshKill} /></Panel>

            <Panel title={`Marché · ${market?.symbol ?? '…'}`}>
              <div className="quote">
                <div><label>Bid</label><strong>{fmt(market?.bid)}</strong></div>
                <div><label>Ask</label><strong>{fmt(market?.ask)}</strong></div>
                <div><label>Spread</label><strong>{fmt(spread)}</strong></div>
              </div>
              <p className="muted">{market?.timestamp ? `Dernier tick ${market.timestamp.slice(11, 19)} UTC` : 'Aucun tick reçu'}</p>
            </Panel>

            <Panel title="Consensus des agents">
              <div className={`consensus ${consensus?.direction ?? 'NO_TRADE'}`}>
                <strong>{LABEL[consensus?.direction ?? 'NO_TRADE']}</strong>
                <span>{consensus ? `${Math.round((consensus.score ?? 0) * 100)} % · ${consensus.agents} agents` : '—'}</span>
              </div>
              <p className="muted">Vote pondéré sur la dernière bougie M5. Information seulement : aucun ordre.</p>
            </Panel>

            <Panel title="Graphique">
              <div className="tabs">
                <button className={tf === 300 ? 'on' : ''} onClick={() => setTf(300)}>M5</button>
                <button className={tf === 60 ? 'on' : ''} onClick={() => setTf(60)}>M1 · scalping</button>
              </div>
              <Candles bars={bars ?? []} />
            </Panel>

            <Panel title="Agents de stratégie">
              {agentsErr && <p className="error">QuestDB indisponible</p>}
              <table className="agents">
                <thead><tr><th>Agent</th><th>Moteur</th><th>Signal</th><th>Entrée</th><th>Stop</th><th>Raison</th></tr></thead>
                <tbody>
                  {(agents ?? []).sort((a, b) => a.agent.localeCompare(b.agent)).map(s => (
                    <tr key={s.agent}>
                      <td>{s.agent}{s.agent.startsWith('scalp') && <em className="danger"> ⚠ scalping</em>}</td>
                      <td>{s.lang}</td>
                      <td><span className={`pill ${ACTION_CLASS[s.action] ?? 'none'}`}>{s.action}</span></td>
                      <td>{fmt(s.entry)}</td><td>{fmt(s.stop_loss)}</td><td className="reason">{s.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            <Panel title="Compte papier">
              <div className="quote">
                <div><label>Capital</label><strong>{fmt(status?.account?.equity)}</strong></div>
                <div><label>P&L du jour</label><strong>{fmt(status?.account?.realized_today)}</strong></div>
                <div><label>Trades du jour</label><strong>{status?.account?.trades_today ?? '—'}</strong></div>
              </div>
              <p className="muted">Stratégie du moteur papier : {status?.strategy ?? '—'} · position : {status?.position ? 'ouverte' : 'aucune'}</p>
            </Panel>
          </div>

          <footer>
            Hinova Digital est un lab de construction logicielle, ni conseiller financier ni éducateur. Le trading comporte un risque élevé
            de perte en capital ; le scalping l'amplifie. Mode papier uniquement : aucun ordre réel n'est envoyé.
          </footer>
        </div>
      </Animator>
    </AnimatorGeneralProvider>
  )
}
