import { useMemo } from 'react'

import { useQuery } from '@tanstack/react-query'
import { Download, Filter, Grid2X2 } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { ProfileScopeBar } from '../components/profile/ProfileScopeBar'
import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { useProfileScopeOptions } from '../hooks/useProfileScopeOptions'
import { exportFailureAnalyticsCsv, getCircuitBreakerEvents, getFailureAnalytics, getSelfLearningProfile } from '../lib/api'
import { downloadFile, exportFilename } from '../lib/export'
import { formatNumber, formatTime, toNumber } from '../lib/format'
import { DEFAULT_PROFILE_SCOPE, normalizeProfileScope } from '../lib/profileScope'
import type {
  FailureAnalyticsPayload,
  FailureBreakdownRow,
  FailureImprovementRow,
  FailureRecord,
  FailureSeverityRow,
  CircuitBreakerEvent,
} from '../lib/types'

const LOOKBACK_OPTIONS = [
  { label: 'Last 7 days', value: '7' },
  { label: 'Last 30 days', value: '30' },
  { label: 'Last 90 days', value: '90' },
  { label: 'All time', value: '0' },
]

const MODE_OPTIONS = [
  { label: 'All modes', value: 'ALL' },
  { label: 'SWING', value: 'SWING' },
  { label: 'SCALP', value: 'SCALP' },
  { label: 'AGGRESSIVE_SCALP', value: 'AGGRESSIVE_SCALP' },
]

const CONFIDENCE_OPTIONS = [
  { label: 'Conf ≥ 0.60', value: '0.6' },
  { label: 'Conf ≥ 0.70', value: '0.7' },
  { label: 'Conf ≥ 0.80', value: '0.8' },
  { label: 'Conf ≥ 0.50', value: '0.5' },
  { label: 'All confidence', value: '0' },
]

function sourceTone(source: string | undefined) {
  switch (String(source ?? '').toUpperCase()) {
    case 'TIMING':
      return 'bg-amber-100 text-amber-900'
    case 'SIGNAL_QUALITY':
      return 'bg-orange-100 text-orange-900'
    case 'RISK_MODEL':
      return 'bg-rose-100 text-rose-900'
    case 'MARKET_CONDITION':
      return 'bg-slate-200 text-slate-800'
    case 'THRESHOLD_LOGIC':
      return 'bg-stone-200 text-stone-800'
    default:
      return 'bg-stone-200 text-stone-800'
  }
}

function componentTone(component: string | undefined) {
  switch (String(component ?? '')) {
    case 'Entry Logic':
      return 'bg-violet-100 text-violet-900'
    case 'Stop Loss':
      return 'bg-rose-100 text-rose-900'
    case 'Take Profit':
      return 'bg-orange-100 text-orange-900'
    default:
      return 'bg-stone-200 text-stone-800'
  }
}

function breakdownBarTone(label: string) {
  switch (label) {
    case 'TIMING':
      return 'bg-amber-500'
    case 'SIGNAL_QUALITY':
      return 'bg-orange-500'
    case 'RISK_MODEL':
      return 'bg-sky-600'
    case 'MARKET_CONDITION':
      return 'bg-slate-500'
    case 'THRESHOLD_LOGIC':
      return 'bg-stone-400'
    case 'Entry Logic':
      return 'bg-violet-500'
    case 'Stop Loss':
      return 'bg-rose-500'
    case 'Take Profit':
      return 'bg-orange-500'
    default:
      return 'bg-stone-400'
  }
}

function severityTone(level: number) {
  if (level >= 5) return 'bg-rose-600'
  if (level >= 4) return 'bg-amber-500'
  if (level >= 3) return 'bg-sky-600'
  if (level >= 2) return 'bg-stone-500'
  return 'bg-stone-300'
}

function confidencePips(confidence: number) {
  const active = Math.max(0, Math.min(5, Math.round(confidence * 5)))
  return Array.from({ length: 5 }, (_, index) => index < active)
}

function timeAgo(value: string | undefined) {
  if (!value) return '--'
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return formatTime(value)
  const deltaMs = Date.now() - timestamp
  const minutes = Math.max(0, Math.round(deltaMs / 60000))
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

function BreakdownCard({
  title,
  items,
}: {
  title: string
  items: FailureBreakdownRow[]
}) {
  const maxCount = Math.max(1, ...items.map((item) => toNumber(item.count, 0)))
  return (
    <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
      <h2 className="text-sm font-semibold text-stone-950">{title}</h2>
      <div className="mt-4 grid gap-3">
        {items.length ? items.map((item) => (
          <div key={String(item.label)} className="grid grid-cols-[110px_minmax(0,1fr)_40px_44px] items-center gap-3 text-sm">
            <span className="truncate text-stone-600">{item.label}</span>
            <div className="h-3 rounded-full bg-stone-100">
              <div
                className={`h-3 rounded-full ${breakdownBarTone(String(item.label ?? ''))}`}
                style={{ width: `${(toNumber(item.count, 0) / maxCount) * 100}%` }}
              />
            </div>
            <span className="text-right font-semibold text-stone-900">{formatNumber(item.count, 0)}</span>
            <span className="text-right text-stone-500">{formatNumber(item.percent, 0)}%</span>
          </div>
        )) : <p className="text-sm text-stone-500">No classified failures in this scope.</p>}
      </div>
    </section>
  )
}

export function FailureAnalyticsRoute() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { options: profileScopeOptions } = useProfileScopeOptions()
  const rawProfileScope = searchParams.get('profile') ?? ''
  const isSimulationScope = rawProfileScope.startsWith('simulation-')
  const profileScope = isSimulationScope ? rawProfileScope : normalizeProfileScope(rawProfileScope, profileScopeOptions)
  const scopeOptions = isSimulationScope
    ? [{ value: profileScope, profile_id: profileScope, label: `Simulation ${profileScope.replace('simulation-', '#')}`, kind: 'profile' as const, enabled: true, description: 'Synthetic profile generated from simulation failure analysis.' }, ...profileScopeOptions]
    : profileScopeOptions
  const lookback = searchParams.get('lookback') ?? (isSimulationScope ? '3650' : '30')
  const mode = searchParams.get('mode') ?? 'ALL'
  const minConfidence = searchParams.get('min_confidence') ?? (isSimulationScope ? '0' : '0.6')
  const highlightedOrderId = searchParams.get('order_id') ?? ''

  const payloadQuery = useQuery({
    queryKey: ['failure-analytics-page', lookback, mode, minConfidence, profileScope],
    queryFn: () => getFailureAnalytics(Number(lookback), mode, Number(minConfidence), profileScope),
    refetchOnWindowFocus: false,
  })
  const circuitEventsQuery = useQuery({
    queryKey: ['failure-analytics-circuit-events', profileScope],
    queryFn: () => getCircuitBreakerEvents(20, 0, profileScope),
    refetchOnWindowFocus: false,
    enabled: !isSimulationScope,
  })
  const selfLearningQuery = useQuery({
    queryKey: ['failure-analytics-self-learning'],
    queryFn: () => getSelfLearningProfile(30),
    refetchOnWindowFocus: false,
  })

  const payload = (payloadQuery.data ?? {}) as FailureAnalyticsPayload
  const summary = payload.summary ?? {}
  const sourceBreakdown = (payload.source_breakdown ?? []) as FailureBreakdownRow[]
  const componentBreakdown = (payload.component_breakdown ?? []) as FailureBreakdownRow[]
  const severityItems = (payload.severity_distribution?.items ?? []) as FailureSeverityRow[]
  const improvements = ((payload.ranked_improvements ?? []) as FailureImprovementRow[]).slice(0, 5)
  const recentFailures = (payload.recent_failures ?? []) as FailureRecord[]
  const circuitEvents = ((circuitEventsQuery.data?.items ?? []) as CircuitBreakerEvent[]) ?? []
  const selfLearningTopActions = (selfLearningQuery.data?.top_recommended_actions_by_regime ?? []).slice(0, 5)
  const matrix = payload.source_component_matrix ?? {}
  const matrixSources = matrix.sources ?? []
  const matrixComponents = matrix.components ?? []
  const matrixCells = matrix.cells ?? {}
  const meaningfulHeatmap = Boolean(payload.meta?.has_meaningful_heatmap)
  const allFilteredOut = Boolean(payload.meta?.all_filtered_out_by_confidence)
  const totalLosses = toNumber(summary.total_losses, 0)
  const analyzedLosses = toNumber(summary.total_losses_analyzed, 0)

  const statCards = useMemo(() => ([
    {
      label: 'Losses analyzed',
      value: formatNumber(summary.total_losses_analyzed, 0),
      sub: `${formatNumber(summary.total_losses, 0)} total losses`,
      tone: 'text-stone-950',
    },
    {
      label: 'Avg realized R',
      value: `${formatNumber(summary.avg_realized_r)}R`,
      sub: 'on analyzed losses',
      tone: toNumber(summary.avg_realized_r, 0) < 0 ? 'text-rose-700' : 'text-teal-700',
    },
    {
      label: 'Top failure source',
      value: String(summary.top_failure_source ?? '--'),
      sub: `${formatNumber(summary.top_failure_source_count, 0)} occurrences`,
      tone: 'text-amber-700',
    },
    {
      label: 'Top blamed component',
      value: String(summary.top_blamed_component ?? '--'),
      sub: `${formatNumber(summary.top_blamed_component_count, 0)} occurrences`,
      tone: 'text-stone-950',
    },
  ]), [summary])

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (!value || value === 'ALL') next.delete(key)
    else next.set(key, value)
    setSearchParams(next, { replace: true })
  }

  function updateProfileScope(value: string) {
    const next = new URLSearchParams(searchParams)
    if (!value || value === DEFAULT_PROFILE_SCOPE) next.delete('profile')
    else next.set('profile', value)
    setSearchParams(next, { replace: true })
  }

  async function handleExport() {
    try {
      const csv = await exportFailureAnalyticsCsv(Number(lookback), mode, Number(minConfidence), profileScope)
      downloadFile(csv, exportFilename('failure-analytics', 'csv'), 'text/csv;charset=utf-8')
      toast.success('Failure analytics CSV downloaded.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to export failures CSV.')
    }
  }

  if (payloadQuery.isLoading && !payloadQuery.data) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading failure analytics..." />
      </AnimatedRoute>
    )
  }

  if (!analyzedLosses && !allFilteredOut && !totalLosses) {
    return (
      <AnimatedRoute>
        <div className="mx-auto grid w-full max-w-[960px] gap-4 px-2 py-2">
          <section className="flex flex-wrap items-start justify-between gap-4 rounded-[1.3rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
            <div className="grid gap-1">
              <h1 className="text-xl font-medium text-stone-950">Failure analytics</h1>
              <p className="text-sm text-stone-500">Why trades are losing — ranked by impact</p>
            </div>
          </section>
          <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/84 p-10 text-center shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
            <p className="text-lg font-semibold text-stone-950">No failures analyzed yet</p>
            <p className="mt-2 text-sm text-stone-500">
              This page populates as losing trades close and get classified. Come back after your first analyzed loss.
            </p>
          </div>
        </div>
      </AnimatedRoute>
    )
  }

  return (
    <AnimatedRoute>
      <div className="mx-auto grid w-full max-w-[960px] gap-4 px-2 py-2">
        <ProfileScopeBar
          options={scopeOptions}
          value={profileScope}
          onChange={updateProfileScope}
        />
        <section className="flex flex-wrap items-start justify-between gap-4 rounded-[1.3rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_16px_32px_rgba(77,62,40,0.06)]">
          <div className="grid gap-1">
            <h1 className="text-xl font-medium text-stone-950">Failure analytics</h1>
            <p className="text-sm text-stone-500">Why trades are losing — ranked by impact</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="grid gap-1 text-xs text-stone-500">
              <span>Lookback</span>
              <select value={lookback} onChange={(event) => updateParam('lookback', event.target.value)} className="h-10 rounded-xl border border-stone-900/8 bg-white px-3 text-sm text-stone-900">
                {LOOKBACK_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label className="grid gap-1 text-xs text-stone-500">
              <span>Mode</span>
              <select value={mode} onChange={(event) => updateParam('mode', event.target.value)} className="h-10 rounded-xl border border-stone-900/8 bg-white px-3 text-sm text-stone-900">
                {MODE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label className="grid gap-1 text-xs text-stone-500">
              <span>Min confidence</span>
              <select value={minConfidence} onChange={(event) => updateParam('min_confidence', event.target.value)} className="h-10 rounded-xl border border-stone-900/8 bg-white px-3 text-sm text-stone-900">
                {CONFIDENCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <button type="button" onClick={() => void handleExport()} className="mt-[18px] inline-flex h-10 items-center gap-2 rounded-xl bg-stone-950 px-4 text-sm font-semibold text-stone-50">
              <Download className="h-4 w-4" />
              Export CSV
            </button>
          </div>
        </section>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {statCards.map((card) => (
            <div key={card.label} className="rounded-[1rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
              <p className="text-xs text-stone-500">{card.label}</p>
              <p className={`mt-2 text-2xl font-semibold tracking-[-0.04em] ${card.tone}`}>{card.value}</p>
              <p className="mt-1 text-xs text-stone-500">{card.sub}</p>
            </div>
          ))}
        </section>

        <div className="grid gap-4 md:grid-cols-2">
          <BreakdownCard title="Failure source breakdown" items={sourceBreakdown} />
          <BreakdownCard title="Blamed component breakdown" items={componentBreakdown} />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <div className="flex items-center gap-2">
              <Grid2X2 className="h-4 w-4 text-stone-700" />
              <h2 className="text-sm font-semibold text-stone-950">Source × component heatmap</h2>
            </div>
            {!meaningfulHeatmap ? (
              <div className="mt-4 rounded-[1rem] border border-dashed border-stone-300 bg-stone-50 px-4 py-6 text-sm text-stone-500">
                Heatmap needs at least 5 analyzed losses to be meaningful.
              </div>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <div className="grid min-w-[560px]" style={{ gridTemplateColumns: `120px repeat(${matrixComponents.length}, minmax(68px, 1fr))` }}>
                  <div />
                  {matrixComponents.map((component) => (
                    <div key={component} className="px-1 pb-2 text-center text-[11px] font-semibold uppercase tracking-[0.12em] text-stone-500">
                      {component}
                    </div>
                  ))}
                  {matrixSources.map((source) => (
                    <div key={source} className="contents">
                      <div key={`${source}-label`} className="pr-2 pt-2 text-xs font-semibold text-stone-600">{source}</div>
                      {matrixComponents.map((component) => {
                        const count = toNumber(matrixCells[source]?.[component], 0)
                        const tone =
                          count >= 14 ? 'bg-rose-600 text-white' :
                          count >= 10 ? 'bg-orange-500 text-white' :
                          count >= 6 ? 'bg-amber-400 text-stone-950' :
                          count >= 3 ? 'bg-amber-100 text-amber-900' :
                          count >= 1 ? 'bg-amber-50 text-amber-800' :
                          'bg-stone-100 text-stone-400'
                        return (
                          <div key={`${source}-${component}`} className={`m-1 flex h-12 items-center justify-center rounded-lg text-sm font-semibold ${tone}`}>
                            {count > 0 ? count : '—'}
                          </div>
                        )
                      })}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Severity distribution</h2>
            <div className="mt-4 grid gap-3">
              {severityItems.map((item) => {
                const count = toNumber(item.count, 0)
                const percent = toNumber(item.percent, 0)
                return (
                  <div key={String(item.severity)} className="grid grid-cols-[14px_84px_minmax(0,1fr)_36px_40px] items-center gap-3 text-sm">
                    <span className={`h-2.5 w-2.5 rounded-full ${severityTone(toNumber(item.severity, 0))}`} />
                    <span className="text-stone-600">Severity {item.severity}</span>
                    <div className="h-3 rounded-full bg-stone-100">
                      <div className={`h-3 rounded-full ${severityTone(toNumber(item.severity, 0))}`} style={{ width: `${percent}%` }} />
                    </div>
                    <span className="text-right font-semibold text-stone-950">{count}</span>
                    <span className="text-right text-stone-500">{formatNumber(percent, 0)}%</span>
                  </div>
                )
              })}
            </div>
            <div className="mt-4 border-t border-stone-900/8 pt-3 text-sm">
              <div className="flex items-center justify-between py-1">
                <span className="text-stone-500">Avg severity</span>
                <span className="font-semibold text-stone-950">{formatNumber(payload.severity_distribution?.avg_severity, 1)} / 5</span>
              </div>
              <div className="flex items-center justify-between py-1">
                <span className="text-stone-500">Avg classifier confidence</span>
                <span className="font-semibold text-stone-950">{formatNumber(payload.severity_distribution?.avg_confidence, 2)}</span>
              </div>
            </div>
          </section>
        </div>

        {allFilteredOut ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1rem] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4" />
              All records are below the current confidence threshold.
            </div>
            <button type="button" onClick={() => updateParam('min_confidence', '0')} className="rounded-full border border-amber-300 px-3 py-1.5 font-semibold">
              Lower confidence filter
            </button>
          </div>
        ) : null}

        <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
          <h2 className="text-sm font-semibold text-stone-950">Top improvement suggestions — ranked by weight score</h2>
          <div className="mt-4 grid gap-3">
            {improvements.length ? improvements.map((item) => (
              <div key={`${item.failure_source}-${item.blamed_component}-${item.improvement}`} className="rounded-[1rem] border border-stone-900/8 bg-stone-50/70 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className={`rounded-full px-2.5 py-1 font-semibold ${sourceTone(item.failure_source)}`}>{item.failure_source}</span>
                  <span className={`rounded-full px-2.5 py-1 font-semibold ${componentTone(item.blamed_component)}`}>{item.blamed_component}</span>
                  <span className="text-stone-500">weight {formatNumber(item.weight_score, 1)}</span>
                </div>
                <p className="mt-2 text-sm leading-6 text-stone-900">{item.improvement}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-stone-500">
                  <span>{formatNumber(item.count, 0)} occurrences</span>
                  <span>·</span>
                  <span>avg severity {formatNumber(item.avg_severity, 1)}</span>
                  <span>·</span>
                  <div className="flex items-end gap-1">
                    {confidencePips(toNumber(item.avg_confidence, 0)).map((active, index) => (
                      <span key={index} className={`h-3 w-1.5 rounded-full ${active ? 'bg-stone-900' : 'bg-stone-300'}`} />
                    ))}
                  </div>
                  <span>{formatNumber(item.avg_confidence, 2)} confidence</span>
                </div>
              </div>
            )) : <p className="text-sm text-stone-500">No ranked improvement suggestions yet for the current confidence threshold.</p>}
          </div>
        </section>

        <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-stone-700" />
            <h2 className="text-sm font-semibold text-stone-950">Advisory alternatives by regime</h2>
          </div>
          <div className="mt-4 grid gap-3">
            {selfLearningTopActions.length ? selfLearningTopActions.map((row, index) => (
              <div key={`${String(row.learning_regime)}-${String(row.action_label)}-${index}`} className="grid gap-2 rounded-[1rem] border border-stone-900/8 bg-stone-50/80 px-4 py-3 md:grid-cols-[1fr_auto_auto] md:items-center">
                <div>
                  <p className="text-sm font-semibold text-stone-950">{String(row.action_label ?? '--')}</p>
                  <p className="text-xs text-stone-500">{String(row.learning_regime ?? '--')}</p>
                </div>
                <span className="text-sm text-stone-500">{formatNumber(row.count, 0)} samples</span>
                <span className={`text-sm font-semibold ${toNumber(row.avg_realized_r) >= 0 ? 'text-teal-800' : 'text-rose-800'}`}>{formatNumber(row.avg_realized_r)}R</span>
              </div>
            )) : <p className="text-sm text-stone-500">No advisory alternatives have been built yet.</p>}
          </div>
        </section>

        <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-stone-950">Recent analyzed losses</h2>
            {analyzedLosses > recentFailures.length ? (
              <Link to="/trades" className="text-sm font-semibold text-teal-800 hover:text-teal-700">View all in Trades</Link>
            ) : null}
          </div>
          <div className="mt-4 grid gap-3">
            {recentFailures.map((row) => {
              const highlighted = highlightedOrderId && highlightedOrderId === String(row.order_id ?? '')
              return (
                <div
                  key={String(row.order_id ?? `${row.symbol}-${row.created_at_utc}`)}
                  className={`rounded-[1rem] border px-4 py-3 ${highlighted ? 'border-amber-400 bg-amber-50/80 shadow-[inset_4px_0_0_0_rgba(217,119,6,0.75)]' : 'border-stone-900/8 bg-stone-50/70'}`}
                >
                  <div className="flex flex-wrap items-start gap-3">
                    <div className="w-16 text-sm font-semibold text-stone-950">{row.symbol ?? '--'}</div>
                    <div className={`w-14 text-right text-sm font-semibold ${toNumber(row.realized_r, 0) < 0 ? 'text-rose-700' : 'text-stone-950'}`}>
                      {formatNumber(row.realized_r)}R
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${sourceTone(row.failure_source)}`}>{row.failure_source}</span>
                        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${componentTone(row.blamed_component)}`}>{row.blamed_component}</span>
                        <span className="rounded-full bg-stone-200 px-2.5 py-1 text-xs font-semibold text-stone-800">sev {row.severity_score}</span>
                        <span className="text-xs text-stone-500">{row.mode ?? '--'} · {row.interval ?? '--'} · {timeAgo(row.created_at_utc)}</span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-stone-600">{row.explanation}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        <section className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-stone-950">Circuit breaker history</h2>
            <span className="text-xs text-stone-500">Past trips with reason, duration, and loss rate at trip time</span>
          </div>
          <div className="mt-4 grid gap-3">
            {isSimulationScope ? (
              <p className="text-sm text-stone-500">Circuit breaker history is live-profile only. This synthetic simulation scope shows failure classifications and improvements only.</p>
            ) : circuitEvents.length ? circuitEvents.map((event) => (
              <div key={String(event.id ?? event.triggered_at_utc ?? Math.random())} className="rounded-[1rem] border border-stone-900/8 bg-stone-50/70 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${String(event.status ?? '') === 'OPEN' ? 'bg-rose-100 text-rose-900' : String(event.status ?? '') === 'DEGRADED' ? 'bg-amber-100 text-amber-900' : 'bg-teal-100 text-teal-900'}`}>{event.status}</span>
                  <span className="text-xs text-stone-500">{timeAgo(event.triggered_at_utc)}</span>
                  <span className="text-xs text-stone-500">{formatNumber(event.failure_rate, 1)}% failure rate</span>
                  <span className="text-xs text-stone-500">{formatNumber(event.consecutive_losses, 0)} consecutive losses</span>
                </div>
                <p className="mt-2 text-sm leading-6 text-stone-600">{String(event.reason ?? '--')}</p>
                <p className="mt-2 text-xs text-stone-500">
                  Duration: {event.resolved_at_utc ? `${timeAgo(event.triggered_at_utc)} → ${timeAgo(event.resolved_at_utc)}` : 'Still active / unresolved'}
                </p>
              </div>
            )) : (
              <p className="text-sm text-stone-500">No circuit breaker events have been recorded yet.</p>
            )}
          </div>
        </section>
      </div>
    </AnimatedRoute>
  )
}
