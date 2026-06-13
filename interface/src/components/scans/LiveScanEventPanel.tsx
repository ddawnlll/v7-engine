import { AlertTriangle, RadioTower, Workflow } from 'lucide-react'

import { formatNumber, formatTime, toNumber } from '../../lib/format'
import type { ScanEvent } from '../../lib/types'
import type { ScanEventConnectionState } from '../../hooks/useScanEventStream'

function eventTone(type: string) {
  const normalized = String(type || '').toUpperCase()
  if (normalized.includes('FAILED') || normalized.includes('TIMED_OUT') || normalized.includes('REJECTED') || normalized.includes('DEGRADED')) return 'bad'
  if (normalized.includes('RUNNING') || normalized.includes('QUEUED') || normalized.includes('PROGRESS') || normalized.includes('STAGE')) return 'warn'
  if (normalized.includes('COMPLETED') || normalized.includes('STARTED')) return 'good'
  return 'neutral'
}

function connectionLabel(state: ScanEventConnectionState) {
  if (state === 'open') return 'live'
  if (state === 'connecting') return 'connecting'
  if (state === 'error') return 'degraded'
  if (state === 'disabled') return 'disabled'
  return 'disconnected'
}

function connectionClass(state: ScanEventConnectionState) {
  if (state === 'open') return 'bg-teal-500/12 text-teal-800'
  if (state === 'connecting') return 'bg-amber-500/12 text-amber-800'
  if (state === 'disabled') return 'bg-stone-100 text-stone-500'
  return 'bg-rose-500/12 text-rose-700'
}

function toneClass(type: string) {
  const tone = eventTone(type)
  if (tone === 'good') return 'bg-teal-500/12 text-teal-800'
  if (tone === 'warn') return 'bg-amber-500/12 text-amber-800'
  if (tone === 'bad') return 'bg-rose-500/12 text-rose-700'
  return 'bg-stone-100 text-stone-600'
}

function eventMessage(event: ScanEvent | null) {
  if (!event) return 'Waiting for scan or inference events. Polling remains the source of truth.'
  return String(event.message || event.reason_code || event.status || event.type || 'Event received')
}

function eventStage(event: ScanEvent | null) {
  if (!event) return '--'
  return String(event.stage || event.status || event.type || '--').replaceAll('_', ' ')
}

function eventProgress(event: ScanEvent | null) {
  if (!event) return null
  const total = toNumber(event.total_tasks, 0)
  const completed = toNumber(event.completed_tasks, 0)
  const percent = event.percent_complete != null
    ? Math.max(0, Math.min(100, toNumber(event.percent_complete, 0)))
    : total > 0 ? Math.max(0, Math.min(100, (completed / total) * 100)) : null
  if (percent == null) return null
  return { total, completed, percent }
}

function queueDepth(event: ScanEvent | null) {
  if (!event) return null
  const metrics = event.queue_metrics && typeof event.queue_metrics === 'object' ? event.queue_metrics : null
  const depth = event.queue_depth ?? (metrics?.queue_depth as number | undefined)
  const limit = event.queue_limit ?? (metrics?.queue_limit as number | undefined)
  if (depth == null && limit == null) return null
  return `${formatNumber(depth ?? 0, 0)}${limit != null ? `/${formatNumber(limit, 0)}` : ''}`
}

export function LiveScanEventPanel({
  latestEvent,
  events,
  connectionState,
  profileId,
  runId,
}: {
  latestEvent: ScanEvent | null
  events: ScanEvent[]
  connectionState: ScanEventConnectionState
  profileId: string
  runId?: string | null
}) {
  const progress = eventProgress(latestEvent)
  const latestInference = events.find((event) => String(event.type ?? '').startsWith('INFERENCE_JOB_')) ?? null
  const errorEvent = events.find((event) => ['SCAN_DEGRADED', 'INFERENCE_JOB_FAILED', 'INFERENCE_JOB_TIMED_OUT', 'INFERENCE_JOB_REJECTED'].includes(String(event.type ?? '').toUpperCase())) ?? null
  const qDepth = queueDepth(latestEvent) ?? queueDepth(latestInference)

  return (
    <div data-testid="live-scan-event-panel" className="rounded-xl border border-teal-800/20 bg-teal-950/[0.04] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-500/10">
            <RadioTower className="h-3.5 w-3.5 text-teal-700" strokeWidth={1.8} />
          </span>
          <div>
            <p className="text-sm font-semibold text-stone-950">Live scan stream</p>
            <p className="text-[0.65rem] text-stone-500">{profileId}{runId ? ` · ${runId}` : ' · profile scoped'}</p>
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
          <span className={`rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wider ${toneClass(String(latestEvent?.type ?? ''))}`}>{eventStage(latestEvent)}</span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg bg-white/70 px-3 py-2">
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Stage</p>
            <p className="mt-0.5 font-medium text-stone-800">{eventStage(latestEvent)}</p>
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2">
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Inference</p>
            <p className="mt-0.5 font-medium text-stone-800">{latestInference ? String(latestInference.type).replace('INFERENCE_JOB_', '').replaceAll('_', ' ') : '--'}</p>
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2">
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Task</p>
            <p className="mt-0.5 font-medium text-stone-800">{latestEvent?.symbol ? `${latestEvent.symbol} · ${latestEvent.interval ?? '--'} · ${latestEvent.mode ?? '--'}` : '--'}</p>
          </div>
          <div className="rounded-lg bg-white/70 px-3 py-2">
            <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Queue</p>
            <p className="mt-0.5 font-medium text-stone-800">{qDepth ?? '--'}</p>
          </div>
        </div>

        {progress ? (
          <div>
            <div className="flex items-center justify-between text-[0.65rem] text-stone-600">
              <span>{formatNumber(progress.completed, 0)}/{formatNumber(progress.total, 0)} tasks</span>
              <span>{formatNumber(progress.percent, 0)}%</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-stone-200">
              <div className="h-full rounded-full bg-teal-500 transition-[width]" style={{ width: `${progress.percent}%` }} />
            </div>
          </div>
        ) : null}

        <div className="rounded-lg bg-white/70 px-3 py-2">
          <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Message</p>
          <p className="mt-0.5 text-xs text-stone-700">{eventMessage(latestEvent)}</p>
          {latestEvent?.timestamp ? <p className="mt-1 text-[0.6rem] text-stone-500">{formatTime(latestEvent.timestamp)}</p> : null}
        </div>

        {errorEvent ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-700">
              <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.8} />
              {String(errorEvent.type).replaceAll('_', ' ')}
            </div>
            <p className="mt-1 text-xs text-rose-600">{String(errorEvent.message || errorEvent.reason_code || 'Realtime stream reported a degraded event.')}</p>
          </div>
        ) : null}

        {connectionState === 'error' || connectionState === 'closed' ? (
          <div className="flex items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <Workflow className="h-3.5 w-3.5" strokeWidth={1.8} />
            Live SSE stream unavailable. EventSource will auto-reconnect; existing scan polling and traces remain active.
          </div>
        ) : null}
      </div>
    </div>
  )
}
