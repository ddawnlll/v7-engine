import { useState } from 'react'
import { AlertTriangle, ClipboardList, ExternalLink, FlaskConical, RadioTower, Workflow } from 'lucide-react'

import { formatNumber, formatTime, toNumber } from '../../lib/format'
import type { SimulationEvent } from '../../lib/types'
import type { SimulationEventConnectionState } from '../../hooks/useSimulationEventStream'

function connectionLabel(state: SimulationEventConnectionState) {
  if (state === 'open') return 'live'
  if (state === 'connecting') return 'connecting'
  if (state === 'error') return 'degraded'
  if (state === 'disabled') return 'disabled'
  return 'disconnected'
}

function connectionClass(state: SimulationEventConnectionState) {
  if (state === 'open') return 'bg-teal-500/12 text-teal-800'
  if (state === 'connecting') return 'bg-amber-500/12 text-amber-800'
  if (state === 'disabled') return 'bg-stone-100 text-stone-500'
  return 'bg-rose-500/12 text-rose-700'
}

function toneClass(type: string) {
  const normalized = String(type || '').toLowerCase()
  if (normalized.includes('failed') || normalized.includes('error')) return 'bg-rose-500/12 text-rose-700'
  if (normalized.includes('progress') || normalized.includes('started') || normalized.includes('created')) return 'bg-amber-500/12 text-amber-800'
  if (normalized.includes('completed')) return 'bg-teal-500/12 text-teal-800'
  if (normalized.includes('stopped')) return 'bg-rose-500/12 text-rose-700'
  return 'bg-stone-100 text-stone-600'
}

function eventMessage(event: SimulationEvent | null) {
  if (!event) return 'Waiting for simulation trace events. HTTP detail remains the reconciliation source.'
  if (event.error) return String(event.error)
  if (event.message) return String(event.message)
  if (event.type === 'trade_settled') {
    const trade = event.trade && typeof event.trade === 'object' ? event.trade as Record<string, unknown> : null
    return `Trade settled${trade?.symbol ? ` · ${String(trade.symbol)}` : ''}${trade?.pnl != null ? ` · P&L ${formatNumber(toNumber(trade.pnl, 0), 2)}` : ''}.`
  }
  const metrics = event.metrics && typeof event.metrics === 'object' ? event.metrics : event.run?.metrics
  const tradeCount = metrics && typeof metrics === 'object' ? metrics.trade_count : null
  if (event.type === 'progress') return `Replay progress update${tradeCount != null ? ` · ${formatNumber(toNumber(tradeCount, 0), 0)} trades` : ''}.`
  if (event.type === 'snapshot') return 'Initial run snapshot received.'
  return String(event.status || event.type || 'Simulation event received')
}

function eventProgress(event: SimulationEvent | null) {
  if (!event) return null
  const metrics = event.metrics && typeof event.metrics === 'object' ? event.metrics : event.run?.metrics
  if (!metrics || typeof metrics !== 'object') return null
  const percent = metrics.progress_pct != null ? Math.max(0, Math.min(100, toNumber(metrics.progress_pct, 0))) : null
  if (percent == null) return null
  return {
    percent,
    trades: toNumber(metrics.trade_count, 0),
    closed: toNumber(metrics.closed_trade_count, 0),
  }
}

export function LiveSimulationEventPanel({
  latestEvent,
  events,
  connectionState,
  runId,
  url,
}: {
  latestEvent: SimulationEvent | null
  events: SimulationEvent[]
  connectionState: SimulationEventConnectionState
  runId?: number | null
  url?: string
}) {
  const [showDetails, setShowDetails] = useState(false)
  const progress = eventProgress(latestEvent)
  const errorEvent = events.find((event) => ['failed', 'error'].includes(String(event.type ?? '').toLowerCase())) ?? null

  return (
    <div data-testid="live-simulation-event-panel" className="rounded-xl border border-teal-800/20 bg-teal-950/[0.04] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-500/10">
            <RadioTower className="h-3.5 w-3.5 text-teal-700" strokeWidth={1.8} />
          </span>
          <div>
            <p className="text-sm font-semibold text-stone-950">Live simulation stream</p>
            <p className="text-[0.65rem] text-stone-500">{runId != null ? `run #${runId}` : 'no selected run'}</p>
          </div>
        </div>
        <span className={`rounded px-2 py-1 text-[0.6rem] font-bold uppercase tracking-wider ${connectionClass(connectionState)}`}>{connectionLabel(connectionState)}</span>
      </div>

      <div className="mt-3 grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white/70 px-3 py-2">
          <div>
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Latest event</p>
            <p className="mt-0.5 text-xs font-semibold text-stone-800">{latestEvent ? String(latestEvent.type).replaceAll('_', ' ') : 'No event yet'}</p>
          </div>
          <span className={`rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wider ${toneClass(String(latestEvent?.type ?? ''))}`}>{String(latestEvent?.status ?? latestEvent?.type ?? '--').replaceAll('_', ' ')}</span>
        </div>

        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="rounded-lg bg-white/70 px-3 py-2">
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Events</p>
            <p className="mt-0.5 font-medium text-stone-800">{formatNumber(events.length, 0)}</p>
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2">
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Trades</p>
            <p className="mt-0.5 font-medium text-stone-800">{progress ? formatNumber(progress.trades, 0) : '--'}</p>
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2">
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Closed</p>
            <p className="mt-0.5 font-medium text-stone-800">{progress ? formatNumber(progress.closed, 0) : '--'}</p>
          </div>
        </div>

        {progress ? (
          <div>
            <div className="flex items-center justify-between text-[0.65rem] text-stone-600">
              <span>Simulation replay</span>
              <span>{formatNumber(progress.percent, 0)}%</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-stone-200">
              <div className="h-full rounded-full bg-teal-500 transition-[width]" style={{ width: `${progress.percent}%` }} />
            </div>
          </div>
        ) : null}

        <div className="rounded-lg bg-white/70 px-3 py-2">
          <div className="flex items-center gap-1.5">
            <FlaskConical className="h-3.5 w-3.5 text-teal-700" strokeWidth={1.8} />
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Message</p>
          </div>
          <p className="mt-0.5 text-xs text-stone-700">{eventMessage(latestEvent)}</p>
          {latestEvent?.timestamp ? <p className="mt-1 text-[0.6rem] text-stone-500">{formatTime(latestEvent.timestamp)}</p> : null}
        </div>

        {errorEvent ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-700">
              <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.8} />
              {String(errorEvent.type).replaceAll('_', ' ')}
            </div>
            <p className="mt-1 text-xs text-rose-600">{String(errorEvent.error || errorEvent.status || 'Simulation stream reported a degraded event.')}</p>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <a
            href="/operate/logs"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-stone-900/8 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 transition hover:bg-stone-950/[0.03]"
          >
            <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.8} />
            Open server logs
          </a>
          <button
            type="button"
            onClick={() => setShowDetails((value) => !value)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-stone-900/8 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 transition hover:bg-stone-950/[0.03]"
          >
            <ClipboardList className="h-3.5 w-3.5" strokeWidth={1.8} />
            {showDetails ? 'Hide detailed output' : 'Detailed output'}
          </button>
        </div>

        {connectionState === 'error' || connectionState === 'closed' ? (
          <div className="flex items-start gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <Workflow className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" strokeWidth={1.8} />
            <span>Live stream unavailable. Simulation detail queries remain available for reconciliation. EventSource will auto-reconnect; open server logs or detailed output to diagnose SSE/proxy/backend state.</span>
          </div>
        ) : null}

        {showDetails ? (
          <div className="rounded-lg border border-stone-900/8 bg-stone-950/[0.03] p-3">
            <div className="grid gap-2 text-xs">
              <div className="grid gap-1">
                <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">SSE URL</p>
                <code className="break-all rounded bg-white px-2 py-1 text-[0.68rem] text-stone-700">{url || '--'}</code>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded bg-white px-2 py-1">
                  <p className="text-[0.6rem] uppercase tracking-widest text-stone-500">Connection</p>
                  <p className="font-semibold text-stone-800">{connectionState}</p>
                </div>
                <div className="rounded bg-white px-2 py-1">
                  <p className="text-[0.6rem] uppercase tracking-widest text-stone-500">Run</p>
                  <p className="font-semibold text-stone-800">{runId ?? '--'}</p>
                </div>
              </div>
              <div className="grid gap-1">
                <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Latest raw event</p>
                <pre className="max-h-48 overflow-auto rounded bg-white p-2 text-[0.65rem] text-stone-700">{latestEvent ? JSON.stringify(latestEvent, null, 2) : 'No SSE event received yet.'}</pre>
              </div>
              <div className="grid gap-1">
                <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Troubleshooting</p>
                <ul className="list-disc space-y-1 pl-4 text-stone-600">
                  <li>Backend must expose <code>/api/v3/simulations/{runId ?? ':id'}/events-sse</code>.</li>
                  <li>If the interface runs on Vite, the hook connects directly to backend port 8000.</li>
                  <li>If this stays disconnected, restart the backend so the simulation SSE route is loaded.</li>
                </ul>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
