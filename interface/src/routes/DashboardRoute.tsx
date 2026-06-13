import { useEffect, useMemo, useState } from 'react'

import {
  Activity,
  Check,
  ArrowRight,
  PlayCircle,
  Workflow,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useSettings } from '../contexts/SettingsContext'
import { useDashboardQuery } from '../hooks/useDashboardQuery'
import { formatNumber, formatTime, statusTone, toNumber } from '../lib/format'

function toneFromStatus(status: string): 'neutral' | 'good' | 'warn' | 'bad' {
  const tone = statusTone(status)
  if (tone === 'tone-good') return 'good'
  if (tone === 'tone-warn') return 'warn'
  if (tone === 'tone-bad') return 'bad'
  return 'neutral'
}

function eventTone(eventType: string, decision: string, isDark: boolean) {
  const text = `${eventType} ${decision}`.toUpperCase()
  if (text.includes('ERROR') || text.includes('FAILED') || text.includes('DEAD')) return isDark ? 'text-rose-300' : 'text-rose-700'
  if (text.includes('CREATED') || text.includes('COMPLETED') || text.includes('CLOSED') || text.includes('HIT_TP')) return isDark ? 'text-teal-300' : 'text-teal-700'
  if (text.includes('SKIPPED') || text.includes('WARNING') || text.includes('PENDING') || text.includes('RUNNING')) return isDark ? 'text-amber-300' : 'text-amber-700'
  return isDark ? 'text-slate-400' : 'text-stone-500'
}

function eventAccentClasses(eventType: string, decision: string, isDark: boolean) {
  const text = `${eventType} ${decision}`.toUpperCase()
  if (text.includes('ERROR') || text.includes('FAILED') || text.includes('DEAD')) return isDark ? 'border-l-rose-400 bg-rose-950/30' : 'border-l-rose-500 bg-rose-50/35'
  if (text.includes('CREATED') || text.includes('COMPLETED') || text.includes('CLOSED') || text.includes('HIT_TP')) return isDark ? 'border-l-teal-400 bg-teal-950/25' : 'border-l-teal-600 bg-teal-50/40'
  if (text.includes('SKIPPED') || text.includes('WARNING') || text.includes('PENDING') || text.includes('RUNNING')) return isDark ? 'border-l-amber-400 bg-amber-950/25' : 'border-l-amber-500 bg-amber-50/40'
  return isDark ? 'border-l-slate-600 bg-slate-900/80' : 'border-l-stone-300 bg-white/88'
}

function summarizeFailure(item: Record<string, unknown>) {
  const result = item.result
  if (typeof result === 'string' && result.trim()) return result
  if (result && typeof result === 'object') {
    const record = result as Record<string, unknown>
    for (const key of ['error_text', 'error', 'message', 'summary']) {
      const value = record[key]
      if (typeof value === 'string' && value.trim()) return value
    }
  }
  return 'No failure detail exposed in the dashboard snapshot.'
}

function buildEventKeys(events: Record<string, unknown>[]) {
  return new Set(
    events.map((event) => [
      String(event.timestamp ?? 'event'),
      String(event.event_type ?? 'EVENT'),
      String(event.decision ?? ''),
      String(event.reason_text ?? ''),
      String(event.symbol ?? ''),
    ].join('::'))
  )
}

export function DashboardRoute() {
  const { settings, term, rawKey } = useSettings()
  const isDark = settings.theme === 'dark'
  const dashboardQuery = useDashboardQuery()
  const { refetch } = dashboardQuery
  const dashboard = dashboardQuery.data ?? null
  const engineHealth = (dashboard?.engine_health ?? {}) as Record<string, unknown>
  const engine = (dashboard?.engine ?? {}) as Record<string, unknown>
  const queue = (dashboard?.job_queue ?? {}) as Record<string, unknown>
  const queueItems = ((queue.items as Record<string, unknown>[] | undefined) ?? []) as Record<string, unknown>[]
  const recentEvents = useMemo(
    () => ((dashboard?.highlights?.recent_events ?? []) as Record<string, unknown>[]),
    [dashboard?.highlights?.recent_events]
  )

  const pending = toNumber(queue.pending, 0)
  const running = toNumber(queue.running, 0)
  const completed = toNumber(queue.completed, 0)
  const failed = toNumber(queue.failed, 0)
  const totalVisibleQueue = Math.max(pending + running + failed, 1)
  const workerCapacity = Math.max(toNumber(engineHealth.worker_capacity, 1), 1)
  const activeWorkers = toNumber(engineHealth.active_workers, 0)
  const queueDepth = toNumber(engineHealth.queue_depth, pending + running + failed)
  const openOrders = toNumber(engineHealth.open_orders, 0)
  const pressureScore = Math.min(100, Math.round(((pending * 1) + (running * 0.5) + (failed * 3)) / workerCapacity * 100))
  const pressureTone = pressureScore >= 80
    ? (isDark ? 'text-rose-200 bg-rose-950/40 border-rose-500/30' : 'text-rose-700 bg-rose-50 border-rose-200')
    : pressureScore >= 45
      ? (isDark ? 'text-amber-200 bg-amber-950/35 border-amber-500/30' : 'text-amber-800 bg-amber-50 border-amber-200')
      : (isDark ? 'text-teal-200 bg-teal-950/35 border-teal-500/30' : 'text-teal-800 bg-teal-50 border-teal-200')
  const failedItems = queueItems.filter((item) => String(item.status ?? '').toUpperCase() === 'FAILED')
  const [showFailures, setShowFailures] = useState(false)
  const shellSectionClass = isDark
    ? 'rounded-[1.7rem] border border-slate-700/60 bg-slate-900/75 px-4 py-4 shadow-[0_20px_52px_rgba(2,6,23,0.42)] backdrop-blur-xl sm:px-5'
    : 'rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_20px_52px_rgba(77,62,40,0.09)] backdrop-blur-xl sm:px-5'
  const heroStripClass = isDark
    ? 'rounded-[1.6rem] border border-slate-700/60 bg-[linear-gradient(135deg,rgba(15,23,42,0.95),rgba(17,24,39,0.88),rgba(8,47,73,0.52))] p-4 shadow-[0_18px_44px_rgba(2,6,23,0.42)]'
    : 'rounded-[1.6rem] border border-stone-900/8 bg-[linear-gradient(135deg,rgba(14,116,144,0.08),rgba(255,255,255,0.9),rgba(245,158,11,0.07))] p-4 shadow-[0_18px_44px_rgba(71,53,29,0.08)]'
  const heroCardClass = isDark
    ? 'rounded-[1.25rem] border border-slate-700/60 bg-slate-900/72 px-4 py-4 shadow-[0_10px_28px_rgba(2,6,23,0.24)]'
    : 'rounded-[1.25rem] border border-white/70 bg-white/78 px-4 py-4 shadow-[0_10px_28px_rgba(71,53,29,0.06)]'
  const panelClass = isDark
    ? 'rounded-[1.6rem] border border-slate-700/60 bg-slate-900/76 p-4 shadow-[0_18px_44px_rgba(2,6,23,0.4)]'
    : 'rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_18px_44px_rgba(71,53,29,0.08)]'
  const eventPanelClass = isDark
    ? 'rounded-[1.6rem] border border-slate-700/60 bg-[linear-gradient(180deg,rgba(15,23,42,0.96),rgba(17,24,39,0.9))] p-4 shadow-[0_18px_44px_rgba(2,6,23,0.42)]'
    : 'rounded-[1.6rem] border border-stone-900/8 bg-[linear-gradient(180deg,rgba(255,255,255,0.9),rgba(248,244,236,0.95))] p-4 shadow-[0_18px_44px_rgba(71,53,29,0.08)]'
  const softCardClass = isDark ? 'rounded-[1.2rem] bg-slate-800/65 p-4' : 'rounded-[1.2rem] bg-stone-950/[0.03] p-4'
  const metricCardClass = isDark ? 'rounded-[1.25rem] bg-slate-800/70 p-4' : 'rounded-[1.25rem] bg-stone-950/[0.03] p-4'
  const pillClass = isDark ? 'rounded-full bg-slate-800/70 px-3 py-2 text-sm text-slate-300' : 'rounded-full bg-stone-950/[0.03] px-3 py-2 text-sm text-stone-600'
  const bannerClass = isDark
    ? 'rounded-[1.35rem] border border-amber-500/30 bg-amber-950/30 px-4 py-3 text-sm text-amber-100 shadow-[0_12px_28px_rgba(120,53,15,0.16)]'
    : 'rounded-[1.35rem] border border-amber-200 bg-amber-50/85 px-4 py-3 text-sm text-amber-900 shadow-[0_12px_28px_rgba(120,53,15,0.08)]'
  const quickNoteClass = isDark
    ? 'rounded-[1.2rem] border border-slate-700/60 bg-slate-900/90 px-4 py-3 text-sm text-slate-300'
    : 'rounded-[1.2rem] border border-stone-900/8 bg-white px-4 py-3 text-sm text-stone-600'
  const linkButtonClass = isDark
    ? 'rounded-[1.2rem] border border-slate-700/60 bg-slate-900/90 px-4 py-3 text-sm font-semibold text-slate-100 transition hover:bg-slate-800/90'
    : 'rounded-[1.2rem] border border-stone-900/8 bg-white px-4 py-3 text-sm font-semibold text-stone-900 transition hover:bg-stone-950/[0.03]'

  const queueSegments = [
    {
      label: 'Pending',
      value: pending,
      width: `${(pending / totalVisibleQueue) * 100}%`,
      classes: 'bg-amber-500/70 text-amber-950',
    },
    {
      label: 'Running',
      value: running,
      width: `${(running / totalVisibleQueue) * 100}%`,
      classes: 'bg-teal-700/80 text-white',
    },
    {
      label: 'Failed',
      value: failed,
      width: `${(failed / totalVisibleQueue) * 100}%`,
      classes: 'bg-rose-600/80 text-white',
    },
  ].filter((segment) => segment.value > 0)
  const [autoRefresh, setAutoRefresh] = useState(settings.refreshInterval ?? 0)
  const [refreshTick, setRefreshTick] = useState(0)
  const [initialEventKeys] = useState(() => buildEventKeys(recentEvents))

  useEffect(() => {
    const timer = window.setInterval(() => {
      setRefreshTick(Date.now())
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (autoRefresh <= 0) return undefined
    const timer = window.setInterval(() => {
      void refetch()
    }, autoRefresh * 1000)
    return () => window.clearInterval(timer)
  }, [autoRefresh, refetch])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        return
      }
      if (event.key.toLowerCase() !== 'r') return
      event.preventDefault()
      void refetch()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [refetch])

  const currentEventKeys = useMemo(() => buildEventKeys(recentEvents), [recentEvents])

  const newEventsCount = useMemo(() => {
    let count = 0
    for (const key of currentEventKeys) {
      if (!initialEventKeys.has(key)) count += 1
    }
    return count
  }, [currentEventKeys, initialEventKeys])

  const dataAgeLabel = useMemo(() => {
    const generatedAt = dashboard?.generated_at
    if (!generatedAt) return '--'
    const ageSeconds = Math.max(0, Math.round((refreshTick - new Date(generatedAt).getTime()) / 1000))
    if (ageSeconds < 60) return `${ageSeconds}s ago`
    const minutes = Math.round(ageSeconds / 60)
    return `${minutes}m ago`
  }, [dashboard?.generated_at, refreshTick])

  const dataAgeMinutes = useMemo(() => {
    const generatedAt = dashboard?.generated_at
    if (!generatedAt) return 0
    return Math.max(0, Math.round((refreshTick - new Date(generatedAt).getTime()) / 60_000))
  }, [dashboard?.generated_at, refreshTick])

  const heroVitals = [
    {
      label: 'Workers',
      value: `${activeWorkers}/${workerCapacity}`,
      detail: activeWorkers >= workerCapacity ? 'At capacity' : 'Capacity available',
    },
    {
      label: 'Queue depth',
      value: formatNumber(queueDepth, 0),
      detail: `${formatNumber(pending, 0)} pending + ${formatNumber(running, 0)} running`,
    },
    {
      label: 'Open orders',
      value: formatNumber(openOrders, 0),
      detail: 'Live paper positions',
    },
    {
      label: 'Pressure',
      value: `${pressureScore}`,
      detail: pressureScore >= 80 ? 'Elevated failure load' : pressureScore >= 45 ? 'Watch queue churn' : 'Nominal load',
    },
  ]

  if (dashboardQuery.isLoading && !dashboard) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading dashboard control room..." />
      </AnimatedRoute>
    )
  }

  return (
      <AnimatedRoute>
      <div className="grid gap-4">
        <section className={shellSectionClass}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex min-w-0 flex-wrap items-center gap-4">
              <div className="flex items-center gap-3">
                <span className={`h-3 w-3 rounded-full ${
                  toneFromStatus(String(engineHealth.status ?? 'unknown')) === 'good'
                    ? 'bg-teal-700'
                    : toneFromStatus(String(engineHealth.status ?? 'unknown')) === 'bad'
                      ? 'bg-rose-700'
                      : toneFromStatus(String(engineHealth.status ?? 'unknown')) === 'warn'
                        ? 'bg-amber-700'
                        : 'bg-stone-400'
                }`} />
                <div className="grid gap-1">
                  <div className="flex flex-wrap items-center gap-3">
                    <p className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">Control Room</p>
                    <StatusBadge label={String(engineHealth.status ?? 'unknown')} tone={toneFromStatus(String(engineHealth.status ?? 'unknown'))} />
                  </div>
                  <p className="text-sm text-stone-600">
                    Last scan {formatTime((engine.last_scan as Record<string, unknown> | undefined)?.timestamp)}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {[
                  ['Worker', String(engine.worker_id ?? '--')],
                  ['Thread', engine.thread_alive ? 'Running' : 'Stopped'],
                ].map(([label, value]) => (
                  <div key={String(label)} className={pillClass}>
                    {label} <span className={isDark ? 'font-semibold text-slate-100' : 'font-semibold text-stone-950'}>{value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className={pillClass}>
                Data age <span className={isDark ? 'font-semibold text-slate-100' : 'font-semibold text-stone-950'}>{dataAgeLabel}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {[0, 30, 60, 120].map((seconds) => (
                  <button
                    key={seconds}
                    type="button"
                    className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
                      autoRefresh === seconds
                        ? 'bg-stone-950 text-stone-50'
                        : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                    }`}
                    onClick={() => setAutoRefresh(seconds)}
                  >
                    {seconds === 0 ? 'Manual' : `${seconds}s`}
                  </button>
                ))}
              </div>
              <Link
                to="/operate/control"
                className="inline-flex items-center justify-center gap-2 rounded-full bg-stone-950 px-5 py-3 text-sm font-semibold text-stone-50 transition hover:-translate-y-0.5 hover:bg-stone-900"
              >
                Open Admin
                <ArrowRight className="h-4 w-4" strokeWidth={1.8} />
              </Link>
            </div>
          </div>
        </section>

        <section className={heroStripClass}>
          <div className="grid gap-3 lg:grid-cols-4">
            {heroVitals.map((item) => (
              <div key={item.label} className={heroCardClass}>
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{item.label}</p>
                <p className={`mt-2 text-3xl font-semibold tracking-[-0.05em] ${isDark ? 'text-slate-50' : 'text-stone-950'}`}>{item.value}</p>
                <p className="mt-2 text-sm text-stone-600">{item.detail}</p>
              </div>
            ))}
          </div>
        </section>

        {dataAgeMinutes >= 5 ? (
          <section className={bannerClass}>
            Data is {dataAgeLabel} old. Consider refreshing if you need a current queue or event view.
          </section>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-[1.6fr_0.9fr]">
          <section className={eventPanelClass}>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">
                <Activity className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
                Event Log
                {newEventsCount > 0 ? (
                  <span className="inline-flex min-w-8 items-center justify-center rounded-full bg-teal-700 px-2.5 py-1 text-[0.68rem] font-semibold tracking-normal text-white">
                    +{formatNumber(newEventsCount, 0)}
                  </span>
                ) : null}
              </div>
              <span className="text-sm text-stone-500">{recentEvents.length} visible</span>
            </div>
            <div className="grid max-h-[44rem] gap-2 overflow-y-auto">
              {recentEvents.length ? recentEvents.map((event, index) => {
                const eventType = String(event.event_type ?? 'EVENT')
                const decision = String(event.decision ?? '')
                const tone = eventTone(eventType, decision, isDark)
                return (
                  <div key={`${String(event.timestamp)}-${index}`} className={`grid gap-2 rounded-[1.15rem] border border-stone-900/6 border-l-[3px] px-4 py-3 ${eventAccentClasses(eventType, decision, isDark)}`}>
                    <div className="flex items-start justify-between gap-4">
                      <div className="grid gap-1">
                        <div className="flex items-center gap-3">
                          <span className={`font-mono text-xs ${tone}`}>{formatTime(event.timestamp)}</span>
                          <span className={`text-sm font-semibold ${tone}`}>{eventType}</span>
                        </div>
                        <p className={`text-sm leading-6 ${isDark ? 'text-slate-200' : 'text-stone-700'}`}>{String(event.reason_text ?? event.symbol ?? 'System event')}</p>
                      </div>
                      <span className={`rounded-full px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.16em] ${tone} bg-stone-950/[0.04]`}>
                        {decision || 'event'}
                      </span>
                    </div>
                  </div>
                )
              }) : <EmptyState message="Engine events will appear here once the trace feed is active." />}
            </div>
          </section>

          <div className="grid gap-4">
            <section className={panelClass}>
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">
                  <Workflow className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
                  Queue Pressure
                </div>
                <div className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${pressureTone}`}>
                  Score {pressureScore}
                </div>
              </div>
              <div className="grid gap-4">
                <div className="h-7 overflow-hidden rounded-full bg-stone-950/[0.06]">
                  <div className="flex h-full w-full">
                    {queueSegments.length ? queueSegments.map((segment) => (
                      <div
                        key={segment.label}
                        className={`flex h-full items-center justify-center text-[0.72rem] font-semibold uppercase tracking-[0.14em] ${segment.classes}`}
                        style={{ width: segment.width }}
                      >
                        {segment.value > 0 ? segment.label : ''}
                      </div>
                    )) : <div className="flex h-full w-full items-center justify-center text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-stone-500">Idle queue</div>}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    { label: term('pending'), value: pending, tone: 'text-amber-800', raw: rawKey('pending') },
                    { label: term('running'), value: running, tone: 'text-teal-800', raw: rawKey('running') },
                    { label: term('completed'), value: completed, tone: 'text-stone-950', raw: rawKey('completed') },
                    { label: term('failed'), value: failed, tone: failed > 0 ? 'text-rose-800' : 'text-stone-500', raw: rawKey('failed') },
                  ].map((item) => (
                    <div key={item.label} className={metricCardClass}>
                      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{item.label}</p>
                      {settings.showRawKeys ? <p className="mt-1 font-mono text-[0.68rem] text-stone-400">{item.raw}</p> : null}
                      <p className={`mt-2 text-3xl font-semibold tracking-[-0.05em] ${item.tone}`}>{formatNumber(item.value, 0)}</p>
                    </div>
                  ))}
                </div>

                <div className="grid gap-3">
                  <div className={softCardClass}>
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Failure drill-down</p>
                        <p className="mt-2 text-sm text-stone-600">
                          {failed > 0 ? 'Inspect failed jobs directly from the dashboard snapshot.' : 'No failed jobs are visible in the current snapshot.'}
                        </p>
                      </div>
                      {failed > 0 ? (
                        <button
                          type="button"
                          className="rounded-full border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-800 transition hover:bg-rose-100"
                          onClick={() => setShowFailures((current) => !current)}
                        >
                          {showFailures ? 'Hide failures' : `Show failures (${formatNumber(failed, 0)})`}
                        </button>
                      ) : null}
                    </div>
                    {showFailures && failed > 0 ? (
                      <div className="mt-4 grid gap-2">
                        {failedItems.length ? failedItems.map((item, index) => (
                          <div key={`${String(item.run_id ?? item.id ?? 'failed')}-${index}`} className={isDark ? 'rounded-[1rem] border border-rose-500/25 bg-slate-900/90 px-3 py-3' : 'rounded-[1rem] border border-rose-200 bg-white px-3 py-3'}>
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className={`text-sm font-semibold ${isDark ? 'text-slate-50' : 'text-stone-950'}`}>{String(item.run_id ?? item.id ?? 'Unknown job')}</p>
                              <span className={isDark ? 'rounded-full bg-rose-950/40 px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-rose-200' : 'rounded-full bg-rose-50 px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-rose-700'}>
                                {String(item.status ?? 'FAILED')}
                              </span>
                            </div>
                            <p className={`mt-2 text-sm leading-6 ${isDark ? 'text-slate-200' : 'text-stone-700'}`}>{summarizeFailure(item)}</p>
                            <p className="mt-2 text-xs text-stone-500">
                              Finished {formatTime(item.finished_at ?? item.created_at)}{item.requested_by ? ` · ${String(item.requested_by)}` : ''}
                            </p>
                          </div>
                        )) : (
                          <div className={isDark ? 'rounded-[1rem] border border-dashed border-rose-500/25 bg-slate-900/90 px-3 py-3 text-sm text-slate-300' : 'rounded-[1rem] border border-dashed border-rose-200 bg-white px-3 py-3 text-sm text-stone-600'}>
                            Failed count is present, but this snapshot does not include per-job failure rows.
                          </div>
                        )}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </section>

            <section className={panelClass}>
              <div className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">
                <PlayCircle className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
                Quick Actions
              </div>
              <div className="grid gap-3">
                <div className={softCardClass}>
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Operator handoff</p>
                  <div className="mt-3 grid gap-2">
                    {[
                      ['Last monitor', formatTime((engine.last_monitor as Record<string, unknown> | undefined)?.timestamp)],
                      ['Generated', formatTime(dashboard?.generated_at)],
                      ['Refresh mode', autoRefresh === 0 ? 'Manual' : `Every ${autoRefresh}s`],
                    ].map(([label, value]) => (
                      <div key={String(label)} className={isDark ? 'flex items-center justify-between gap-3 rounded-[0.95rem] bg-slate-900/90 px-3 py-2.5 text-sm' : 'flex items-center justify-between gap-3 rounded-[0.95rem] bg-white px-3 py-2.5 text-sm'}>
                        <span className="text-stone-500">{label}</span>
                        <span className={isDark ? 'font-semibold text-slate-50' : 'font-semibold text-stone-950'}>{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className={quickNoteClass}>
                  <div className={`flex items-center gap-2 ${isDark ? 'text-slate-100' : 'text-stone-950'}`}>
                    <Check className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
                    Press <span className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-xs">R</span> to refresh immediately.
                  </div>
                  <p className="mt-2 leading-6">Use Admin for diagnostics and queue actions, Portfolio for current exposure, and Simulations for replay review.</p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Link
                    to="/portfolio"
                    className={linkButtonClass}
                  >
                    Open Portfolio
                  </Link>
                  <Link
                    to="/simulations"
                    className={linkButtonClass}
                  >
                    Open Simulations
                  </Link>
                </div>
              </div>
            </section>
          </div>
        </div>

        {settings.showApiInspector ? (
          <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_18px_44px_rgba(71,53,29,0.08)]">
            <div className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-stone-500">API Response Inspector</div>
            <pre className="max-h-[28rem] overflow-auto rounded-[1.2rem] bg-stone-950 px-4 py-4 text-xs leading-6 text-stone-200">
              {JSON.stringify(dashboard, null, 2)}
            </pre>
          </section>
        ) : null}
      </div>
    </AnimatedRoute>
  )
}
