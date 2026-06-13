import { useEffect, useMemo, useState } from 'react'

import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowRight,
  Clock3,
  CircleAlert,
  OctagonX,
  Pause,
  Play,
  Radar,
  Search,
  Sparkles,
  Square,
  Workflow,
  Copy,
  ChevronDown,
  ChevronUp,
  Download,
  AlertTriangle,
} from 'lucide-react'

import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { StatusBadge } from '../components/ui/StatusBadge'
import { ScanJobForm } from '../components/forms/ScanJobForm'
import { ProfileScopeBar } from '../components/profile/ProfileScopeBar'
import { LiveScanEventPanel } from '../components/scans/LiveScanEventPanel'
import { AlertBanner, BreakdownList, MetricTile, SectionHeader, SkipBar, SortHeader, ToolbarBtn } from '../components/analytics/RuntimeDiagnostics'
import { useSettings } from '../contexts/SettingsContext'
import { useQueueScanMutation } from '../hooks/useQueueScanMutation'
import { useProfileScopeOptions } from '../hooks/useProfileScopeOptions'
import { useScanEventStream } from '../hooks/useScanEventStream'
import {
  pauseScans, resumeScans, fetchJobsForScope, fetchRuntimeSettingsForScope,
  fetchSymbols, fetchTracesForScope, forceStopAllScans, stopAllScans, stopScans,
} from '../lib/api'
import { copyToClipboard, downloadFile, exportAsCSV, exportFilename } from '../lib/export'
import { formatNumber, formatTime, statusTone, toNumber } from '../lib/format'
import { DEFAULT_PROFILE_SCOPE, normalizeProfileScope } from '../lib/profileScope'
import { queryClient } from '../lib/queryClient'
import type { JobItem, JobQueueSnapshot, JsonRecord, ProfileScopeValue, ScanControlState } from '../lib/types'
import { toast } from 'sonner'

// ─── types ────────────────────────────────────────────────────────────────────

type ScanFilter = 'ALL' | 'ACTIVE' | 'COMPLETED' | 'FAILED'
type SignalLearningRow = JsonRecord & {
  confidenceRaw: number; confidenceFinal: number; confidenceDelta: number
  learningActive: boolean; selfLearningActive: boolean; selfLearningBypassed: boolean
  selfLearningBypassReason: string; componentPenalty: number; entryPenalty: number
  executionPenalty: number; calibrationStatus: string; bucketLabel: string
  topPenaltyLabel: string; topPenaltyValue: number
}
type SkipTraceRow = {
  traceId: string; timestamp: string; symbol: string; interval: string; mode: string
  direction: string; stage: string; reasonCode: string; reasonText: string; summary: string
  noTradeReason: string; skipFamily: 'DIRECTIONAL' | 'NEUTRAL'; confidenceRaw: number | null; confidenceFinal: number | null
  confidenceDelta: number | null; probabilityRaw: number | null; probabilityFinal: number | null
  qualityMultiplier: number | null; learningPenaltyPts: number | null
  observabilityScoreBreakdown: JsonRecord | null; probabilityModel: JsonRecord | null
  decisionPath: JsonRecord | null; rawRecord: JsonRecord
}
type DecisionDetailRow = {
  id: string; detailType: 'SIGNAL' | 'SKIP'; symbol: string; interval: string
  mode: string; direction: string; confidenceRaw: number | null; confidenceFinal: number | null
  confidenceDelta: number | null; probabilityRaw: number | null; probabilityFinal: number | null
  learningLabel: string; learningDetail: string; outcome: string; summary: string
  observabilityScoreBreakdown: JsonRecord | null; probabilityModel: JsonRecord | null
  decisionPath: JsonRecord | null; rawRecord: JsonRecord
}
type DecisionSortKey = 'type' | 'symbol' | 'interval' | 'mode' | 'direction' | 'confidence' | 'learning' | 'outcome' | 'summary'
type SkipTraceSortKey = 'symbol' | 'mode' | 'stage' | 'reason' | 'confidence' | 'suppression'

// ─── constants ────────────────────────────────────────────────────────────────

const INTERVAL_OPTION_CATALOG = ['15m','30m','1h','2h','4h','6h','12h','1d','3d','7d','14d','1M'] as const
const STRATEGY_MODE_OPTIONS = ['SCALP','SWING','AGGRESSIVE_SCALP'] as const

// ─── pure helpers ─────────────────────────────────────────────────────────────

function splitCsv(value: unknown) {
  return String(value ?? '').split(',').map(s => s.trim()).filter(Boolean)
}
function modeIntervalSettingKey(mode: string) {
  return `AUTONOMOUS_INTERVALS_${String(mode).toUpperCase()}`
}
function preferLargerSymbolUniverse(primary: string[] | undefined, fallback: string[]) {
  const p = Array.isArray(primary) ? primary.map(String) : []
  return p.length >= fallback.length ? p : fallback
}
function scanJobKey(job: JobItem) {
  const id = String(job.id ?? '').trim(); if (id) return id
  const r = String(job.run_id ?? '').trim(); if (r) return r
  return String(job.created_at ?? '')
}
function badgeTone(status: string): 'neutral' | 'good' | 'warn' | 'bad' {
  const t = statusTone(status)
  return t === 'tone-good' ? 'good' : t === 'tone-warn' ? 'warn' : t === 'tone-bad' ? 'bad' : 'neutral'
}
function durationSeconds(job: JobItem) {
  const s = job.started_at ? new Date(String(job.started_at)) : null
  const f = job.finished_at ? new Date(String(job.finished_at)) : null
  if (!s || !f || isNaN(s.getTime()) || isNaN(f.getTime())) return null
  return Math.max(0, (f.getTime() - s.getTime()) / 1000)
}
function formatRelativeTime(value: unknown) {
  if (!value) return '--'
  const d = new Date(String(value)); if (isNaN(d.getTime())) return '--'
  const s = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
function progressSnapshot(result: JsonRecord) {
  const p = (result.progress ?? {}) as JsonRecord
  const total = toNumber(p.total_tasks, 0)
  const completed = toNumber(p.completed_tasks, 0)
  const remaining = toNumber(p.remaining_tasks, Math.max(0, total - completed))
  const pct = total > 0 ? Math.max(0, Math.min(100, toNumber(p.percent_complete, (completed / total) * 100))) : 0
  return { totalTasks: total, completedTasks: completed, remainingTasks: remaining, percentComplete: pct, currentTask: (p.current_task ?? null) as JsonRecord | null }
}
function stopDiagnosis(job: JobItem | null, result: JsonRecord, debug: JsonRecord) {
  if (!job) return null
  const status = String(job.status ?? '').toUpperCase()
  const skipped = (result.skipped ?? {}) as JsonRecord
  const totalSkipped = Object.values(skipped).reduce<number>((s, v) => s + toNumber(v, 0), 0)
  const throttled = toNumber(skipped.symbol_throttled, 0)
  const analysisCount = toNumber((((result.timing ?? {}) as JsonRecord).analysis as JsonRecord)?.count, 0)
  const fetchCount = toNumber((((result.timing ?? {}) as JsonRecord).market_fetch as JsonRecord)?.count, 0)
  const p = (result.progress ?? {}) as JsonRecord
  const completed = toNumber(p.completed_tasks, 0); const total = toNumber(p.total_tasks, 0)
  const stopCause = String(result.stop_cause ?? '')
  const stopBy = String(result.stop_requested_by ?? '')
  if (Boolean(result.stale_cancelled)) return { tone: 'warning' as const, title: 'Run was stale-cancelled', message: `The reconcile path cancelled this run after no progress for 5 minutes. Last progress reason was ${String(debug.last_progress_reason ?? '--')}.` }
  if (status === 'STOPPED' || Boolean(result.stopped)) {
    if (stopCause === 'force_stop_requested' || Boolean(result.force_stopped)) return { tone: 'bad' as const, title: 'Run was force-stopped', message: `The runtime aborted this scan immediately${stopBy ? ` by ${stopBy}` : ''}. This is intended for stuck scans and may leave in-flight worker work cancelled rather than gracefully drained.` }
    if (stopCause === 'stop_requested') return { tone: 'warning' as const, title: 'Run was stopped by control action', message: `This run did not fail inside analysis. A stop request${stopBy ? ` from ${stopBy}` : ''} stopped it at ${completed}/${total} tasks.` }
    return { tone: 'warning' as const, title: 'Run stopped before completion', message: `The run stopped at ${completed}/${total} tasks. The current payload shows no execution error, so this looks like an external stop rather than an analyzer failure.` }
  }
  if ((status === 'FAILED' || status === 'DEAD_LETTER' || status === 'DEGRADED') && analysisCount <= 0 && fetchCount <= 0 && throttled > 0 && totalSkipped === completed) return { tone: 'warning' as const, title: 'No analysis work was reached', message: 'All completed tasks were skipped before market fetch or analysis, mostly due to universe throttling. This does not point to slow analyzer execution.' }
  if (status === 'FAILED' || status === 'DEAD_LETTER' || status === 'DEGRADED') return { tone: 'bad' as const, title: 'Run ended with execution errors', message: 'Inspect the error list, fetch timing, and debug payload. This run produced a non-success status with actual execution failures.' }
  return null
}
function dailyCapWarning(result: JsonRecord) {
  const created = toNumber(result.created_orders, 0)
  const capReached = Boolean(result.cap_reached)
  const skipped = (result.skipped ?? {}) as JsonRecord
  const capSkipped = toNumber(skipped.daily_cap_reached, 0)
  if (created > 0) return null
  if (!capReached && capSkipped <= 0) return null
  return { dailyTrades: toNumber(result.daily_trades, 0), dailyCapSkipped: capSkipped }
}
function jobGroupLabel(value: unknown) {
  if (!value) return 'Unknown'
  const d = new Date(String(value)); if (isNaN(d.getTime())) return 'Unknown'
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1)
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  if (target.getTime() === today.getTime()) return 'Today'
  if (target.getTime() === yesterday.getTime()) return 'Yesterday'
  return 'Earlier'
}
function isActiveStatus(status: string) { return ['PENDING','RUNNING','PAUSED','RETRY','STOPPING'].includes(status) }
function statusColor(status: string) {
  if (status === 'COMPLETED') return 'bg-teal-500'
  if (['FAILED','DEAD_LETTER','STOPPED'].includes(status)) return 'bg-rose-500'
  if (['RUNNING','PAUSED','PENDING','RETRY','STOPPING'].includes(status)) return 'bg-amber-500'
  return 'bg-zinc-400'
}
function consecutiveFailureCount(jobs: JobItem[]) {
  const ordered = [...jobs].sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')))
  let count = 0
  for (const job of ordered) {
    const s = String(job.status ?? '').toUpperCase()
    if (['FAILED','DEAD_LETTER','STOPPED'].includes(s)) { count++; continue }
    break
  }
  return count
}
function skipTone(key: string) {
  if (key === 'errors') return 'bg-rose-500'
  if (key === 'daily_cap_reached') return 'bg-amber-500'
  if (key === 'duplicate_open') return 'bg-sky-500'
  if (key === 'market_unavailable') return 'bg-fuchsia-500'
  if (key === 'low_confidence') return 'bg-zinc-500'
  if (key === 'missing_levels') return 'bg-orange-500'
  return 'bg-teal-500'
}
function normalizeSkipRows(skipSummary: JsonRecord) {
  const rows = Object.entries(skipSummary).map(([key, value]) => ({ key, count: toNumber(value, 0) })).filter(r => r.count > 0).sort((a, b) => b.count - a.count)
  const total = rows.reduce((s, r) => s + r.count, 0)
  return rows.map(r => ({ ...r, percent: total > 0 ? (r.count / total) * 100 : 0 }))
}
function signalRows(result: JsonRecord) {
  return (Array.isArray(result.signals) ? result.signals as JsonRecord[] : []).sort((a, b) => toNumber(b.confidence, 0) - toNumber(a.confidence, 0))
}
function average(values: number[]) { return values.length ? values.reduce((s, v) => s + v, 0) / values.length : 0 }
function summarizeDecisionConfidenceRows(rows: Array<{ confidenceRaw: number | null; confidenceFinal: number | null; confidenceDelta: number | null; probabilityRaw?: number | null; probabilityFinal?: number | null }>) {
  const raw = rows.map(r => r.confidenceRaw).filter((v): v is number => v != null)
  const fin = rows.map(r => r.confidenceFinal).filter((v): v is number => v != null)
  const del = rows.map(r => r.confidenceDelta).filter((v): v is number => v != null)
  const pRaw = rows.map(r => r.probabilityRaw).filter((v): v is number => v != null)
  const pFin = rows.map(r => r.probabilityFinal).filter((v): v is number => v != null)
  return { total_rows: rows.length, rows_with_raw_confidence: raw.length, rows_with_final_confidence: fin.length, rows_with_confidence_delta: del.length, rows_with_raw_probability: pRaw.length, rows_with_final_probability: pFin.length, avg_confidence_raw: raw.length ? average(raw) : null, avg_confidence_final: fin.length ? average(fin) : null, avg_confidence_delta: del.length ? average(del) : null, avg_probability_raw: pRaw.length ? average(pRaw) : null, avg_probability_final: pFin.length ? average(pFin) : null }
}
function analysisOverview(result: JsonRecord) {
  const timing = (result.timing ?? {}) as JsonRecord
  const analysis = (timing.analysis ?? {}) as JsonRecord
  const stages = (timing.stages ?? {}) as JsonRecord
  const analysisTasks = toNumber((stages.analysis_tasks ?? analysis.count), 0)
  const fallbacks = toNumber(stages.analysis_fallbacks, 0)
  const signalsEmitted = toNumber(stages.signals_emitted, toNumber(result.counts && (result.counts as JsonRecord).total, 0))
  const createdOrders = toNumber(result.created_orders, toNumber(stages.orders_created, 0))
  const skipped = (result.skipped ?? {}) as JsonRecord
  const neutralSkips = toNumber(skipped.neutral, 0)
  const skipTotal = Object.values(skipped).reduce<number>((s, v) => s + toNumber(v, 0), 0)
  return { analysisAvgMs: toNumber(analysis.avg_ms, 0), analysisP95Ms: toNumber(analysis.p95_ms, 0), analysisP99Ms: toNumber(analysis.p99_ms, 0), analysisTasks, fallbacks, fallbackRatePct: analysisTasks > 0 ? (fallbacks / analysisTasks) * 100 : 0, signalsEmitted, createdOrders, orderConversionPct: signalsEmitted > 0 ? (createdOrders / signalsEmitted) * 100 : 0, neutralSkips, neutralSkipPct: skipTotal > 0 ? (neutralSkips / skipTotal) * 100 : 0 }
}
function signalLearningRows(result: JsonRecord) {
  return signalRows(result).map((row) => {
    const adv = (row.advanced_analysis ?? {}) as JsonRecord
    const learn = (adv.learning_adjustments ?? {}) as JsonRecord
    const self = (adv.self_learning ?? {}) as JsonRecord
    const dp = (adv.decision_path ?? {}) as JsonRecord
    const penalties = [{ label: 'Component', value: toNumber(learn.component_penalty, 0) }, { label: 'Entry', value: toNumber(learn.entry_penalty, 0) }, { label: 'Execution', value: toNumber(learn.execution_penalty, 0) }].filter(p => p.value > 0).sort((a, b) => b.value - a.value)
    return { ...row, confidenceRaw: toNumber(row.confidence_raw, toNumber(dp.confidence_raw, 0)), confidenceFinal: toNumber(row.confidence, toNumber(dp.confidence_final, 0)), confidenceDelta: toNumber(row.confidence, toNumber(dp.confidence_final, 0)) - toNumber(row.confidence_raw, toNumber(dp.confidence_raw, 0)), learningActive: Boolean(learn.learning_active), selfLearningActive: Boolean(self.self_learning_active), selfLearningBypassed: Boolean(self.self_learning_bypassed), selfLearningBypassReason: String(self.bypass_reason ?? '--'), componentPenalty: toNumber(learn.component_penalty, 0), entryPenalty: toNumber(learn.entry_penalty, 0), executionPenalty: toNumber(learn.execution_penalty, 0), calibrationStatus: String(learn.calibration_monotonicity_status ?? learn.calibration_mode ?? '--'), bucketLabel: String(learn.bucket_label ?? '--'), topPenaltyLabel: penalties.length ? penalties[0].label : '--', topPenaltyValue: penalties.length ? penalties[0].value : 0 } as SignalLearningRow
  })
}
function signalLearningOverview(result: JsonRecord) {
  const rows = signalLearningRows(result)
  return { rows, signalCount: rows.length, avgConfidenceRaw: average(rows.map(r => r.confidenceRaw)), avgConfidenceFinal: average(rows.map(r => r.confidenceFinal)), avgConfidenceDelta: average(rows.map(r => r.confidenceDelta)), avgComponentPenalty: average(rows.map(r => r.componentPenalty)), avgEntryPenalty: average(rows.map(r => r.entryPenalty)), avgExecutionPenalty: average(rows.map(r => r.executionPenalty)), learningActiveCount: rows.filter(r => r.learningActive).length, selfLearningActiveCount: rows.filter(r => r.selfLearningActive).length, selfLearningBypassedCount: rows.filter(r => r.selfLearningBypassed).length }
}
function changeText(current: number, previous: number, digits = 1, suffix = '') {
  const d = current - previous; return `${d > 0 ? '+' : ''}${formatNumber(d, digits)}${suffix}`
}
function skipTraceRows(items: JsonRecord[]) {
  return items.map((item) => {
    const payload = (item.signal_payload ?? {}) as JsonRecord
    const advanced = ((payload.advanced_analysis ?? {}) as JsonRecord)
    const details = (item.details ?? {}) as JsonRecord
    const dp = (((advanced.decision_path ?? payload.decision_path) ?? {}) as JsonRecord)
    const learn = (((advanced.learning_adjustments ?? payload.learning_adjustments) ?? {}) as JsonRecord)
    const obs = (((advanced.observability ?? payload.observability) ?? {}) as JsonRecord)
    const probModel = (((advanced.probability_model ?? payload.probability_model) ?? {}) as JsonRecord)
    const direction = String(item.direction ?? payload.direction ?? '--')
    const reasonCode = String(item.reason_code ?? '--')
    const cRaw = payload.confidence_raw != null ? toNumber(payload.confidence_raw, 0) : (dp.confidence_raw != null ? toNumber(dp.confidence_raw, 0) : null)
    const cFin = item.confidence != null ? toNumber(item.confidence, 0) : (payload.confidence_final != null ? toNumber(payload.confidence_final, 0) : (dp.confidence_final != null ? toNumber(dp.confidence_final, 0) : null))
    const pRaw = payload.probability_raw != null ? toNumber(payload.probability_raw, 0) : (dp.probability_raw != null ? toNumber(dp.probability_raw, 0) : null)
    const pFin = payload.probability_final != null ? toNumber(payload.probability_final, 0) : (payload.probability != null ? toNumber(payload.probability, 0) : (dp.probability_final != null ? toNumber(dp.probability_final, 0) : null))
    const comp = toNumber(learn.component_penalty, 0); const entry = toNumber(learn.entry_penalty, 0); const exec = toNumber(learn.execution_penalty, 0)
    const skipFamily: 'DIRECTIONAL' | 'NEUTRAL' = direction === 'NEUTRAL' || reasonCode === 'NEUTRAL' || reasonCode === 'PREFILTER_NEUTRAL' ? 'NEUTRAL' : 'DIRECTIONAL'
    return { traceId: String(item.trace_id ?? ''), timestamp: String(item.timestamp ?? ''), symbol: String(item.symbol ?? payload.symbol ?? '--'), interval: String(item.interval ?? payload.interval ?? '--'), mode: String(item.mode ?? payload.mode ?? '--'), direction, stage: String(details.stage ?? dp.runtime_stage ?? dp.neutral_stage ?? dp.stage ?? 'UNKNOWN'), reasonCode, reasonText: String(item.reason_text ?? '--'), summary: String(payload.summary ?? item.reason_text ?? '--'), noTradeReason: String(payload.no_trade_reason ?? '--'), skipFamily, confidenceRaw: cRaw, confidenceFinal: cFin, confidenceDelta: cRaw != null && cFin != null ? cFin - cRaw : null, probabilityRaw: pRaw, probabilityFinal: pFin, qualityMultiplier: dp.quality_multiplier != null ? toNumber(dp.quality_multiplier, 0) : null, learningPenaltyPts: comp || entry || exec ? (comp + entry + exec) * 100 : null, observabilityScoreBreakdown: (obs.score_breakdown ?? null) as JsonRecord | null, probabilityModel: Object.keys(probModel).length ? probModel : null, decisionPath: Object.keys(dp).length ? dp : null, rawRecord: item } as SkipTraceRow
  })
}
function breakdownRows(rows: Array<{ key: string }>) {
  const counts = new Map<string, number>()
  for (const r of rows) counts.set(r.key, (counts.get(r.key) ?? 0) + 1)
  const total = rows.length
  return [...counts.entries()].map(([key, count]) => ({ key, count, percent: total > 0 ? (count / total) * 100 : 0 })).sort((a, b) => b.count - a.count)
}
function stageTimingRows(result: JsonRecord) {
  const stages = ((((result.timing ?? {}) as JsonRecord).stages ?? {}) as JsonRecord)
  return [['analysis','Analysis'],['market_fetch_total','Fetch total'],['market_fetch_live','Live fetch'],['market_fetch_cache_load','Cache load'],['market_persist','Candle persist'],['indicator_build','Indicator build'],['htf_resolve','HTF resolve'],['signal_audit','Audit build'],['signal_persist','Signal persist'],['signal_attribution','Signal attribution'],['execution','Execution']].map(([key, label]) => ({ key, label, stats: ((stages[key] ?? {}) as JsonRecord) })).filter(r => toNumber(r.stats.count, 0) > 0)
}
function timelineItems(jobs: JobItem[]) {
  const since = Date.now() - 24 * 60 * 60 * 1000
  return jobs.filter(j => { const v = new Date(String(j.created_at ?? '')).getTime(); return isFinite(v) && v >= since }).sort((a, b) => String(a.created_at ?? '').localeCompare(String(b.created_at ?? '')))
}
function compareText(a: unknown, b: unknown) {
  return String(a ?? '').localeCompare(String(b ?? ''), undefined, { sensitivity: 'base' })
}
function compareNumber(a: number | null | undefined, b: number | null | undefined) {
  return (a ?? Number.NEGATIVE_INFINITY) - (b ?? Number.NEGATIVE_INFINITY)
}

// ─── sub-components ───────────────────────────────────────────────────────────

// ─── main page ────────────────────────────────────────────────────────────────

export function ScansRoute() {
  const { settings } = useSettings()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { options: profileScopeOptions } = useProfileScopeOptions()
  const profileScope = normalizeProfileScope(searchParams.get('profile'), profileScopeOptions)
  const darkMode = settings.theme === 'dark'
  const [filter, setFilter] = useState<ScanFilter>('ALL')
  const [query, setQuery] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [selectionMode, setSelectionMode] = useState<'auto' | 'manual'>('auto')
  const [detailQuery, setDetailQuery] = useState('')
  const [builderOpen, setBuilderOpen] = useState(false)
  const [showAllSymbols, setShowAllSymbols] = useState(false)
  const [decisionSortKey, setDecisionSortKey] = useState<DecisionSortKey>('confidence')
  const [decisionSortDescending, setDecisionSortDescending] = useState(true)
  const [skipTraceSortKey, setSkipTraceSortKey] = useState<SkipTraceSortKey>('confidence')
  const [skipTraceSortDescending, setSkipTraceSortDescending] = useState(true)

  const jobsQuery = useQuery({ queryKey: ['scan-jobs-history', profileScope], queryFn: () => fetchJobsForScope(250, profileScope), refetchInterval: 10_000 })
  const runtimeSettingsQuery = useQuery({ queryKey: ['runtime-settings', 'scans-route', profileScope], queryFn: () => fetchRuntimeSettingsForScope(profileScope), refetchInterval: 30_000 })
  const symbolsQuery = useQuery({ queryKey: ['symbols', 'scans-route'], queryFn: fetchSymbols, refetchInterval: 60_000 })
  const [selectedTraceLimit] = useState(5000)
  const queueMutation = useQueueScanMutation(profileScope)

  const pauseMutation = useMutation({ mutationFn: () => pauseScans('scans_route', profileScope), onSuccess: async () => { toast.success('Scan pause requested'); await Promise.all([queryClient.invalidateQueries({ queryKey: ['scan-jobs-history', profileScope] }), queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }), queryClient.invalidateQueries({ queryKey: ['engine-health'] })]) }, onError: (e) => toast.error('Failed to pause scans', { description: e instanceof Error ? e.message : 'Unknown error' }) })
  const resumeMutation = useMutation({ mutationFn: () => resumeScans('scans_route', profileScope), onSuccess: async () => { toast.success('Scan resume requested'); await Promise.all([queryClient.invalidateQueries({ queryKey: ['scan-jobs-history', profileScope] }), queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }), queryClient.invalidateQueries({ queryKey: ['engine-health'] })]) }, onError: (e) => toast.error('Failed to resume scans', { description: e instanceof Error ? e.message : 'Unknown error' }) })
  const stopMutation = useMutation({ mutationFn: () => stopScans('scans_route', profileScope), onSuccess: async () => { toast.success('Stop requested for active scan'); await Promise.all([queryClient.invalidateQueries({ queryKey: ['scan-jobs-history', profileScope] }), queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }), queryClient.invalidateQueries({ queryKey: ['engine-health'] })]) }, onError: (e) => toast.error('Failed to stop scan', { description: e instanceof Error ? e.message : 'Unknown error' }) })
  const stopAllMutation = useMutation({ mutationFn: () => stopAllScans('scans_route', profileScope), onSuccess: async (p) => { const a = (p.affected_run_ids ?? []).filter(Boolean); toast.success(a.length ? `Stop-all requested for ${a.length} active scan${a.length === 1 ? '' : 's'}` : 'Stop-all requested'); await Promise.all([queryClient.invalidateQueries({ queryKey: ['scan-jobs-history', profileScope] }), queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }), queryClient.invalidateQueries({ queryKey: ['engine-health'] })]) }, onError: (e) => toast.error('Failed to stop all scans', { description: e instanceof Error ? e.message : 'Unknown error' }) })
  const forceStopAllMutation = useMutation({ mutationFn: () => forceStopAllScans('scans_route', profileScope), onSuccess: async (p) => { const a = (p.affected_run_ids ?? []).filter(Boolean); toast.success(a.length ? `Force-stop requested for ${a.length} scan${a.length === 1 ? '' : 's'}` : 'Force-stop requested'); await Promise.all([queryClient.invalidateQueries({ queryKey: ['scan-jobs-history', profileScope] }), queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }), queryClient.invalidateQueries({ queryKey: ['engine-health'] })]) }, onError: (e) => toast.error('Failed to force-stop scans', { description: e instanceof Error ? e.message : 'Unknown error' }) })

  const snapshot = (jobsQuery.data ?? {}) as JobQueueSnapshot
  const runtimeSettings = (runtimeSettingsQuery.data ?? {}) as Record<string, string>
  const jobs = (snapshot.items ?? []) as JobItem[]
  const scanControl = ((snapshot.control ?? {}) as ScanControlState)
  const scanControlStatus = String(scanControl.active_status ?? 'IDLE').toUpperCase()
  const desiredScanState = String(scanControl.desired_state ?? 'RUNNING').toUpperCase()
  const isScanPaused = desiredScanState === 'PAUSED'
  const fallbackActiveJob = jobs.find(j => ['RUNNING','PAUSED','STOPPING'].includes(String(j.status ?? '').toUpperCase())) ?? null
  const activeScanRunId = String(scanControl.active_run_id ?? fallbackActiveJob?.run_id ?? '').trim() || null
  const hasActiveScan = Boolean(activeScanRunId)
  const effectiveScanControlStatus = hasActiveScan && scanControlStatus === 'IDLE' ? String(fallbackActiveJob?.status ?? 'RUNNING').toUpperCase() : scanControlStatus

  const filteredJobs = useMemo(() => {
    const term = query.trim().toUpperCase()
    return jobs.filter(job => {
      const status = String(job.status ?? '').toUpperCase()
      const payload = (job.payload ?? {}) as JsonRecord
      const symbols = Array.isArray(payload.symbols) ? payload.symbols.map(s => String(s).toUpperCase()) : []
      const matchesQuery = !term ? true : symbols.some(s => s.includes(term)) || String(job.run_id ?? '').toUpperCase().includes(term)
      const matchesFilter = filter === 'ALL' ? true : filter === 'ACTIVE' ? ['PENDING','RUNNING','PAUSED','RETRY','STOPPING'].includes(status) : filter === 'FAILED' ? ['FAILED','DEAD_LETTER'].includes(status) : status === 'COMPLETED'
      return matchesQuery && matchesFilter
    })
  }, [filter, jobs, query])

  const groupedJobs = useMemo(() => {
    const groups = new Map<string, JobItem[]>()
    for (const job of filteredJobs) {
      const label = jobGroupLabel(job.created_at)
      groups.set(label, [...(groups.get(label) ?? []), job])
    }
    return ['Today','Yesterday','Earlier','Unknown']
      .map(label => ({
        label,
        jobs: [...(groups.get(label) ?? [])].sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? ''))),
      }))
      .filter(g => g.jobs.length)
  }, [filteredJobs])

  useEffect(() => {
    if (!filteredJobs.length) { setSelectedJobId(null); setSelectionMode('auto'); return }
    if (!selectedJobId || !filteredJobs.some(j => scanJobKey(j) === selectedJobId)) { setSelectedJobId(scanJobKey(filteredJobs[0])); setSelectionMode('auto') }
  }, [filteredJobs, selectedJobId])

  useEffect(() => {
    if (selectionMode !== 'auto' || !hasActiveScan || !activeScanRunId) return
    const activeJob = filteredJobs.find(j => String(j.run_id ?? '') === activeScanRunId)
    if (!activeJob) return
    const nextId = scanJobKey(activeJob)
    if (selectedJobId === nextId) return
    setSelectedJobId(nextId)
    queueMicrotask(() => document.getElementById(`scan-job-${nextId}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
  }, [activeScanRunId, filteredJobs, hasActiveScan, selectedJobId, selectionMode])

  useEffect(() => {
    setShowAllSymbols(false)
  }, [selectedJobId])

  const selectedJob = filteredJobs.find(j => scanJobKey(j) === selectedJobId) ?? null
  const selectedRunId = String(selectedJob?.run_id ?? '').trim()
  const selectedJobIsActive = selectedJob ? isActiveStatus(String(selectedJob.status ?? '').toUpperCase()) : false
  const liveScanRunId = activeScanRunId || (selectedJobIsActive ? selectedRunId : null)
  const liveScanEvents = useScanEventStream({ profileScope, runId: liveScanRunId })
  const scanTracesQuery = useQuery({ queryKey: ['scan-traces', profileScope, selectedRunId, selectedTraceLimit], queryFn: () => fetchTracesForScope(selectedTraceLimit, { runId: selectedRunId, eventType: 'SCAN_SKIPPED', profileScope }), enabled: Boolean(selectedRunId), refetchInterval: 10_000 })
  const selectedPayload = (selectedJob?.payload ?? {}) as JsonRecord
  const selectedResult = (selectedJob?.result ?? {}) as JsonRecord
  const jobSymbols = Array.isArray(selectedPayload.symbols) ? selectedPayload.symbols.map(String) : []
  const jobIntervals = Array.isArray(selectedPayload.intervals) ? selectedPayload.intervals.map(String) : []
  const jobModes = Array.isArray(selectedPayload.modes) ? selectedPayload.modes.map(String) : []
  const skipSummary = (selectedResult.skipped ?? {}) as JsonRecord

  const filteredCounts = useMemo(() => {
    const c = { jobs: filteredJobs.length, pending: 0, running: 0, paused: 0, completed: 0, failed: 0 }
    for (const j of filteredJobs) {
      const s = String(j.status ?? '').toUpperCase()
      if (['PENDING','RETRY'].includes(s)) c.pending++
      else if (s === 'RUNNING') c.running++
      else if (s === 'PAUSED' || s === 'STOPPING') c.paused++
      else if (s === 'COMPLETED') c.completed++
      else if (['FAILED','DEAD_LETTER'].includes(s)) c.failed++
    }
    return c
  }, [filteredJobs])

  const selectedDuration = selectedJob ? durationSeconds(selectedJob) : null
  const selectedError = String(selectedJob?.error_text ?? '').trim()
  const selectedProgress = progressSnapshot(selectedResult)
  const selectedDebug = (selectedResult.debug ?? {}) as JsonRecord
  const selectedScope = (selectedResult.scope ?? {}) as JsonRecord
  const selectedDiagnosis = stopDiagnosis(selectedJob, selectedResult, selectedDebug)
  const selectedDailyCapWarning = dailyCapWarning(selectedResult)
  const selectedStageRows = useMemo(() => stageTimingRows(selectedResult), [selectedResult])
  const selectedSignals = useMemo(() => signalLearningOverview(selectedResult).rows.filter(row => { const term = detailQuery.trim().toUpperCase(); if (!term) return true; const h = `${row.symbol} ${row.interval} ${row.mode} ${row.direction} ${row.summary}`.toUpperCase(); return h.includes(term) }), [detailQuery, selectedResult])
  const skipRows = useMemo(() => normalizeSkipRows(skipSummary), [skipSummary])
  const skipTotal = useMemo(() => skipRows.reduce((s, r) => s + r.count, 0), [skipRows])
  const failureStreak = useMemo(() => consecutiveFailureCount(jobs), [jobs])
  const recentTimeline = useMemo(() => timelineItems(jobs), [jobs])
  const selectedAnalysisOverview = useMemo(() => analysisOverview(selectedResult), [selectedResult])
  const selectedLearningOverview = useMemo(() => signalLearningOverview(selectedResult), [selectedResult])
  const orderedJobs = useMemo(() => [...jobs].sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? ''))), [jobs])
  const selectedPreviousJob = useMemo(() => { if (!selectedJob) return null; const idx = orderedJobs.findIndex(j => scanJobKey(j) === scanJobKey(selectedJob)); return idx < 0 || idx === orderedJobs.length - 1 ? null : orderedJobs[idx + 1] }, [orderedJobs, selectedJob])
  const selectedPreviousResult = (selectedPreviousJob?.result ?? {}) as JsonRecord
  const previousAnalysisOverview = useMemo(() => analysisOverview(selectedPreviousResult), [selectedPreviousResult])
  const previousLearningOverview = useMemo(() => signalLearningOverview(selectedPreviousResult), [selectedPreviousResult])
  const selectedSkipTraceRows = useMemo(() => skipTraceRows(((scanTracesQuery.data?.items ?? []) as JsonRecord[])), [scanTracesQuery.data?.items])
  const selectedSkipStageBreakdown = useMemo(() => breakdownRows(selectedSkipTraceRows.map(r => ({ key: r.stage }))), [selectedSkipTraceRows])
  const selectedSkipReasonBreakdown = useMemo(() => breakdownRows(selectedSkipTraceRows.map(r => ({ key: r.reasonCode }))), [selectedSkipTraceRows])
  const selectedSkipConfidenceStats = useMemo(() => {
    const summarize = (rows: SkipTraceRow[]) => {
      const raw = rows.map(r => r.confidenceRaw).filter((v): v is number => v != null)
      const fin = rows.map(r => r.confidenceFinal).filter((v): v is number => v != null)
      const del = rows.map(r => r.confidenceDelta).filter((v): v is number => v != null)
      const pen = rows.map(r => r.learningPenaltyPts).filter((v): v is number => v != null)
      return { avgRaw: average(raw), avgFinal: average(fin), avgDelta: average(del), avgLearningPenaltyPts: average(pen), withConfidenceCount: raw.length, count: rows.length }
    }
    const directional = selectedSkipTraceRows.filter(r => r.skipFamily === 'DIRECTIONAL')
    const neutral = selectedSkipTraceRows.filter(r => r.skipFamily === 'NEUTRAL')
    return { overall: summarize(selectedSkipTraceRows), directional: summarize(directional), neutral: summarize(neutral) }
  }, [selectedSkipTraceRows])

  const selectedVenueQueueRows = useMemo(() => selectedSignals
    .map((row, index) => {
      const outcome = (row.execution_outcome ?? {}) as JsonRecord
      const submissionStatus = String(outcome.submission_status ?? outcome.signal_outcome ?? '').toUpperCase()
      const orderId = String(outcome.order_id ?? '')
      if (!submissionStatus && !orderId) return null
      return {
        id: orderId || `${String(row.symbol ?? '--')}-${index}`,
        symbol: String(row.symbol ?? '--'),
        interval: String(row.interval ?? '--'),
        mode: String(row.mode ?? '--'),
        submissionStatus,
        orderStatus: String(outcome.order_status ?? '--'),
        orderId,
        venueOrderId: String(outcome.venue_order_id ?? '--'),
        clientOrderId: String(outcome.client_order_id ?? '--'),
      }
    })
    .filter((row): row is NonNullable<typeof row> => Boolean(row)), [selectedSignals])

  const selectedDecisionRows = useMemo<DecisionDetailRow[]>(() => {
    const sRows = selectedSignals.map((row, i) => ({
      id: `signal-${String(row.symbol ?? '--')}-${String(row.interval ?? '--')}-${String(row.mode ?? '--')}-${i}`,
      detailType: 'SIGNAL' as const, symbol: String(row.symbol ?? '--'), interval: String(row.interval ?? '--'), mode: String(row.mode ?? '--'), direction: String(row.direction ?? '--'),
      confidenceRaw: row.confidenceRaw, confidenceFinal: row.confidenceFinal, confidenceDelta: row.confidenceDelta,
      probabilityRaw: ((row.advanced_analysis as JsonRecord | undefined)?.probability_raw != null) ? toNumber((row.advanced_analysis as JsonRecord | undefined)?.probability_raw, 0) : null,
      probabilityFinal: row.probability != null ? toNumber(row.probability, 0) : ((row.advanced_analysis as JsonRecord | undefined)?.probability_final != null) ? toNumber((row.advanced_analysis as JsonRecord | undefined)?.probability_final, 0) : null,
      learningLabel: row.learningActive ? 'Learning active' : 'Learning quiet',
      learningDetail: `${row.topPenaltyLabel} ${row.topPenaltyValue > 0 ? `${formatNumber(row.topPenaltyValue * 100, 2)} pts` : '--'} · ${row.calibrationStatus}`,
      outcome: String((row.execution_outcome as JsonRecord | undefined)?.signal_outcome ?? (row.execution_outcome as JsonRecord | undefined)?.outcome_label ?? row.no_trade_reason ?? 'SIGNAL'),
      summary: String(row.summary ?? '--'),
      observabilityScoreBreakdown: (((row.advanced_analysis as JsonRecord | undefined)?.observability ?? {}) as JsonRecord).score_breakdown as JsonRecord | null ?? null,
      probabilityModel: ((((row.advanced_analysis as JsonRecord | undefined)?.probability_model ?? {}) as JsonRecord)),
      decisionPath: ((((row.advanced_analysis as JsonRecord | undefined)?.decision_path ?? {}) as JsonRecord)),
      rawRecord: row as unknown as JsonRecord,
    }))
    const term = detailQuery.trim().toUpperCase()
    const kRows = selectedSkipTraceRows.map(row => ({
      id: `skip-${row.traceId}`, detailType: 'SKIP' as const, symbol: row.symbol, interval: row.interval, mode: row.mode, direction: row.direction,
      confidenceRaw: row.confidenceRaw, confidenceFinal: row.confidenceFinal, confidenceDelta: row.confidenceDelta, probabilityRaw: row.probabilityRaw, probabilityFinal: row.probabilityFinal,
      learningLabel: row.stage.replaceAll('_', ' '), learningDetail: row.learningPenaltyPts != null ? `${formatNumber(row.learningPenaltyPts, 2)} pts learning penalty` : 'No learning penalty captured',
      outcome: row.reasonCode.replaceAll('_', ' '), summary: row.noTradeReason !== '--' ? row.noTradeReason : row.summary,
      observabilityScoreBreakdown: row.observabilityScoreBreakdown, probabilityModel: row.probabilityModel, decisionPath: row.decisionPath, rawRecord: row.rawRecord,
    })).filter(row => { if (!term) return true; const h = `${row.symbol} ${row.interval} ${row.mode} ${row.direction} ${row.outcome} ${row.summary}`.toUpperCase(); return h.includes(term) })
    return [...sRows, ...kRows].sort((a, b) => { if (a.detailType !== b.detailType) return a.detailType === 'SIGNAL' ? -1 : 1; return (b.confidenceFinal ?? -1) - (a.confidenceFinal ?? -1) })
  }, [detailQuery, selectedSignals, selectedSkipTraceRows])

  const sortedDecisionRows = useMemo(() => {
    const rows = [...selectedDecisionRows]
    rows.sort((a, b) => {
      let result = 0
      switch (decisionSortKey) {
        case 'type': result = compareText(a.detailType, b.detailType); break
        case 'symbol': result = compareText(a.symbol, b.symbol); break
        case 'interval': result = compareText(a.interval, b.interval); break
        case 'mode': result = compareText(a.mode, b.mode); break
        case 'direction': result = compareText(a.direction, b.direction); break
        case 'confidence': result = compareNumber(a.confidenceFinal, b.confidenceFinal); break
        case 'learning': result = compareText(`${a.learningLabel} ${a.learningDetail}`, `${b.learningLabel} ${b.learningDetail}`); break
        case 'outcome': result = compareText(a.outcome, b.outcome); break
        case 'summary': result = compareText(a.summary, b.summary); break
      }
      return decisionSortDescending ? -result : result
    })
    return rows
  }, [decisionSortDescending, decisionSortKey, selectedDecisionRows])

  const sortedSkipTraceRows = useMemo(() => {
    const rows = [...selectedSkipTraceRows]
    rows.sort((a, b) => {
      let result = 0
      switch (skipTraceSortKey) {
        case 'symbol': result = compareText(a.symbol, b.symbol); break
        case 'mode': result = compareText(a.mode, b.mode); break
        case 'stage': result = compareText(a.stage, b.stage); break
        case 'reason': result = compareText(a.reasonCode, b.reasonCode); break
        case 'confidence': result = compareNumber(a.confidenceFinal, b.confidenceFinal); break
        case 'suppression': result = compareNumber(a.learningPenaltyPts, b.learningPenaltyPts); break
      }
      return skipTraceSortDescending ? -result : result
    })
    return rows
  }, [selectedSkipTraceRows, skipTraceSortDescending, skipTraceSortKey])

  const selectedDecisionConfidenceSummary = useMemo(() => summarizeDecisionConfidenceRows(sortedDecisionRows), [sortedDecisionRows])

  const availableSymbols = useMemo(() => {
    const live = Array.isArray(symbolsQuery.data?.symbols) ? symbolsQuery.data.symbols.map(String) : []
    return preferLargerSymbolUniverse(live, splitCsv(runtimeSettings.AUTONOMOUS_SYMBOLS))
  }, [runtimeSettings.AUTONOMOUS_SYMBOLS, symbolsQuery.data?.symbols])
  const configuredIntervals = useMemo(() => splitCsv(runtimeSettings.AUTONOMOUS_INTERVALS), [runtimeSettings.AUTONOMOUS_INTERVALS])
  const availableIntervals = useMemo(() => [...new Set([...(configuredIntervals.length ? configuredIntervals : []), ...INTERVAL_OPTION_CATALOG])], [configuredIntervals])
  const enabledModes = useMemo(() => splitCsv(runtimeSettings.AUTONOMOUS_MODES), [runtimeSettings.AUTONOMOUS_MODES])
  const availableModes = useMemo(() => [...new Set([...(enabledModes.length ? enabledModes : []), ...STRATEGY_MODE_OPTIONS])], [enabledModes])
  const modeIntervalPolicy = useMemo(() => Object.fromEntries(availableModes.map(mode => { const c = splitCsv(runtimeSettings[modeIntervalSettingKey(mode)]); return [mode, c.length ? c : configuredIntervals] })), [availableModes, configuredIntervals, runtimeSettings])
  const shellBg = darkMode ? 'text-slate-100' : 'text-stone-900'
  const cardBg = darkMode ? 'bg-slate-900/88' : 'bg-white/84'
  const paneBg = darkMode ? 'bg-slate-900/72' : 'bg-white/70'
  const softPanelBg = darkMode ? 'bg-slate-950/55' : 'bg-stone-950/[0.03]'
  const tableFrameBg = darkMode ? 'bg-slate-950/35' : 'bg-white/80'
  const tableHeadBg = darkMode ? 'bg-slate-950/70' : 'bg-stone-50/80'
  const tableHeadBgSoft = darkMode ? 'bg-slate-950/60' : 'bg-stone-50/70'
  const subtleBorder = darkMode ? 'border-white/10' : 'border-stone-900/8'
  const subtleText = darkMode ? 'text-slate-300' : 'text-stone-700'
  const mutedText = darkMode ? 'text-slate-400' : 'text-stone-500'
  const strongText = darkMode ? 'text-slate-100' : 'text-stone-950'

  function buildScanSummary() {
    if (!selectedJob) return null
    return { id: selectedJob.id, run_id: selectedJob.run_id, status: selectedJob.status, created_at: selectedJob.created_at, started_at: selectedJob.started_at, finished_at: selectedJob.finished_at, symbols: jobSymbols.length, intervals: jobIntervals.length, modes: jobModes.length, created_orders: selectedAnalysisOverview.createdOrders, signals_emitted: selectedAnalysisOverview.signalsEmitted, analysis_avg_ms: selectedAnalysisOverview.analysisAvgMs, analysis_p95_ms: selectedAnalysisOverview.analysisP95Ms, analysis_p99_ms: selectedAnalysisOverview.analysisP99Ms, fallback_rate_pct: selectedAnalysisOverview.fallbackRatePct, neutral_skip_pct: selectedAnalysisOverview.neutralSkipPct, avg_signal_confidence_raw: selectedLearningOverview.avgConfidenceRaw, avg_signal_confidence_final: selectedLearningOverview.avgConfidenceFinal, avg_signal_confidence_delta: selectedLearningOverview.avgConfidenceDelta, skip_total: skipTotal, top_skip_stages: selectedSkipStageBreakdown.slice(0, 8), top_skip_reasons: selectedSkipReasonBreakdown.slice(0, 8), traced_skip_count: selectedSkipTraceRows.length, avg_traced_skip_confidence_raw: selectedSkipConfidenceStats.overall.withConfidenceCount ? selectedSkipConfidenceStats.overall.avgRaw : null, avg_traced_skip_confidence_final: selectedSkipConfidenceStats.overall.withConfidenceCount ? selectedSkipConfidenceStats.overall.avgFinal : null, avg_traced_skip_confidence_delta: selectedSkipConfidenceStats.overall.withConfidenceCount ? selectedSkipConfidenceStats.overall.avgDelta : null, avg_decision_confidence_raw: selectedDecisionConfidenceSummary.avg_confidence_raw, avg_decision_confidence_final: selectedDecisionConfidenceSummary.avg_confidence_final, avg_decision_confidence_delta: selectedDecisionConfidenceSummary.avg_confidence_delta, avg_decision_probability_raw: selectedDecisionConfidenceSummary.avg_probability_raw, avg_decision_probability_final: selectedDecisionConfidenceSummary.avg_probability_final, decision_rows_with_final_confidence: selectedDecisionConfidenceSummary.rows_with_final_confidence, decision_detail_rows: sortedDecisionRows.length, diagnosis: selectedDiagnosis }
  }

  async function copyScope() { if (!jobSymbols.length) { toast.error('No symbols available to copy.'); return }; await copyToClipboard(jobSymbols.join(',')); toast.success('Scan symbol scope copied.') }
  async function copyDetails() { if (!selectedJob) { toast.error('No selected scan to copy.'); return }; await copyToClipboard(JSON.stringify({ id: selectedJob.id, run_id: selectedJob.run_id, status: selectedJob.status, diagnosis: selectedDiagnosis, confidence_summary: selectedDecisionConfidenceSummary, scan_summary: buildScanSummary(), payload: selectedPayload, result: selectedResult }, null, 2)); toast.success('Scan job details copied.') }
  async function copyDrilldownResults() { if (!selectedJob || !sortedDecisionRows.length) { toast.error('No selected scan to copy.'); return }; await copyToClipboard(JSON.stringify(sortedDecisionRows, null, 2)); toast.success('Per-symbol drill-down copied.') }
  function downloadDrilldownCsv() { if (!sortedDecisionRows.length) { toast.error('No per-symbol drill-down rows available.'); return }; downloadFile(exportAsCSV(sortedDecisionRows as unknown as JsonRecord[]), exportFilename(`scan-${selectedRunId || 'results'}-drilldown`, 'csv'), 'text/csv;charset=utf-8'); toast.success('Per-symbol drill-down CSV downloaded.') }
  function downloadScanSummaryJson() { const s = buildScanSummary(); if (!s) { toast.error('No selected scan summary to export.'); return }; downloadFile(JSON.stringify(s, null, 2), exportFilename(`scan-${selectedRunId || 'results'}-summary`, 'json'), 'application/json'); toast.success('Scan summary JSON downloaded.') }

  if (jobsQuery.isLoading && !jobsQuery.data) {
    return <AnimatedRoute><EmptyState message="Loading scan history..." /></AnimatedRoute>
  }

  return (
    <AnimatedRoute>
      <div className={`flex min-h-screen flex-col gap-4 ${shellBg}`}>
        <ProfileScopeBar
          options={profileScopeOptions}
          value={profileScope}
          onChange={(nextValue: ProfileScopeValue) => {
            const nextParams = new URLSearchParams(searchParams)
            if (nextValue === DEFAULT_PROFILE_SCOPE) {
              nextParams.delete('profile')
            } else {
              nextParams.set('profile', nextValue)
            }
            setSearchParams(nextParams)
          }}
        />

        {/* ── TOP HEADER ── */}
        <header className={`rounded-[1.8rem] border px-6 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)] ${subtleBorder} ${cardBg}`}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-500/15">
                <Radar className={`h-4 w-4 ${darkMode ? 'text-teal-300' : 'text-teal-600'}`} strokeWidth={1.8} />
              </div>
              <div>
                <h1 className={`text-sm font-bold tracking-tight ${strongText}`}>Scan History</h1>
                <p className={`text-xs ${mutedText}`}>Every persisted market scan run with scope, outcome, and signal path</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold tabular-nums ${hasActiveScan ? 'bg-teal-500/12 text-teal-800' : 'bg-stone-100 text-stone-500'}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${hasActiveScan ? 'bg-teal-600' : 'bg-stone-400'}`} />
                {hasActiveScan ? `Scan ${effectiveScanControlStatus}` : 'Idle'}
              </span>
              <Link to="/operate/control" className="inline-flex items-center gap-1.5 rounded-lg bg-teal-500/10 px-3 py-1.5 text-xs font-semibold text-teal-800 transition hover:bg-teal-500/20">
                Admin Controls <ArrowRight className="h-3 w-3" strokeWidth={2} />
              </Link>
            </div>
          </div>

          {/* ── STATS ROW ── */}
          <div className="mt-4 flex flex-wrap gap-px overflow-hidden rounded-xl border border-stone-900/8 bg-stone-200/60">
            {([
              ['Total', filteredCounts.jobs, ''],
              ['Pending', filteredCounts.pending, filteredCounts.pending > 0 ? 'text-amber-400' : ''],
              ['Running', filteredCounts.running, filteredCounts.running > 0 ? (darkMode ? 'text-teal-300' : 'text-teal-700') : ''],
              ['Paused', filteredCounts.paused, filteredCounts.paused > 0 ? (darkMode ? 'text-amber-300' : 'text-amber-700') : ''],
              ['Completed', filteredCounts.completed, darkMode ? 'text-teal-300' : 'text-teal-700'],
              ['Failed', filteredCounts.failed, filteredCounts.failed > 0 ? 'text-rose-400' : ''],
            ] as [string, number, string][]).map(([label, value, color]) => (
              <div key={label} className="flex min-w-[100px] flex-1 items-center justify-between gap-3 bg-white/85 px-4 py-3">
                <span className="text-[0.65rem] font-medium uppercase tracking-widest text-stone-500">{label}</span>
                <span className={`text-lg font-bold tabular-nums ${color || 'text-stone-700'}`}>{formatNumber(value, 0)}</span>
              </div>
            ))}
          </div>

          {/* ── FAILURE STREAK BANNER ── */}
          {failureStreak >= 3 ? (
            <div className={`mt-3 flex items-center justify-between gap-3 rounded-xl border px-4 py-2.5 ${darkMode ? 'border-amber-500/25 bg-amber-500/10' : 'border-amber-200 bg-amber-50/90'}`}>
              <div className={`flex items-center gap-2 text-xs ${darkMode ? 'text-amber-200' : 'text-amber-800'}`}>
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" strokeWidth={1.8} />
                <span><strong>{formatNumber(failureStreak, 0)} consecutive failures</strong> — check engine health before trusting new queue activity</span>
              </div>
              <Link to="/operate/control" className={`shrink-0 text-xs font-semibold ${darkMode ? 'text-amber-300 hover:text-amber-200' : 'text-amber-700 hover:text-amber-900'}`}>Review →</Link>
            </div>
          ) : null}

          {/* ── TIMELINE ── */}
          <div className="mt-3">
            <div className="flex items-center justify-between gap-3">
              <p className={`text-[0.65rem] font-medium uppercase tracking-widest ${mutedText}`}>Last 24h · {formatNumber(recentTimeline.length, 0)} runs</p>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {recentTimeline.length
                ? recentTimeline.map(job => {
                    const status = String(job.status ?? '').toUpperCase()
                    const key = scanJobKey(job)
                    return (
                      <button key={key} type="button" onClick={() => { setSelectedJobId(key); setSelectionMode('manual') }}
                        className={`h-2 w-6 rounded-sm transition hover:opacity-70 hover:scale-110 ${statusColor(status)}`}
                        title={`${formatTime(job.created_at)} · ${status}`}
                      />
                    )
                  })
                : <span className="text-xs text-stone-500">No scans in the last 24 hours.</span>}
            </div>
          </div>
        </header>

        {/* ── MAIN 3-COLUMN BODY ── */}
        {/*
          ASCII layout:
          ┌──────────────┬──────────────────────────────┬────────────────────────┐
          │  JOB LIST    │  SELECTED JOB DETAIL         │  DRILL-DOWN            │
          │  280px fixed │  scrollable, ~420px           │  scrollable, flex-1    │
          └──────────────┴──────────────────────────────┴────────────────────────┘
        */}
        <div className={`mt-4 flex flex-1 overflow-hidden rounded-[1.8rem] border shadow-[0_18px_40px_rgba(77,62,40,0.08)] ${subtleBorder} ${cardBg}`} style={{ height: 'calc(100vh - 260px)' }}>

          {/* ── COLUMN 1: JOB LIST ── */}
          <aside className={`flex w-72 shrink-0 flex-col border-r ${subtleBorder} ${paneBg}`}>
            {/* search + filters */}
            <div className={`border-b p-3 ${subtleBorder}`}>
              <label className="relative flex items-center">
                <Search className="pointer-events-none absolute left-3 h-3.5 w-3.5 text-stone-400" strokeWidth={1.8} />
                <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Symbol or run ID…"
                  className={`h-8 w-full rounded-lg border pl-9 pr-3 text-xs outline-none placeholder:text-stone-400 focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6 ${subtleBorder} ${darkMode ? 'bg-slate-950/60 text-slate-100' : 'bg-white text-stone-900'}`}
                />
              </label>
              <div className="mt-2 flex gap-1">
                {(['ALL','ACTIVE','COMPLETED','FAILED'] as ScanFilter[]).map(f => (
                  <button key={f} type="button" onClick={() => setFilter(f)}
                    className={`flex-1 rounded-md py-1 text-[0.6rem] font-semibold uppercase tracking-wider transition ${filter === f ? 'bg-teal-500/12 text-teal-800' : 'text-stone-500 hover:bg-stone-950/[0.03] hover:text-stone-950'}`}
                  >{f}</button>
                ))}
              </div>
            </div>

            {/* job list */}
            <div className="flex-1 overflow-y-auto p-2">
              {groupedJobs.length ? groupedJobs.map(group => (
                <div key={group.label}>
                  <p className="px-2 pb-1 pt-3 text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">{group.label}</p>
                  {group.jobs.map(job => {
                    const key = scanJobKey(job)
                    const selected = key === selectedJobId
                    const payload = (job.payload ?? {}) as JsonRecord
                    const result = (job.result ?? {}) as JsonRecord
                    const symbols = Array.isArray(payload.symbols) ? payload.symbols.map(String) : []
                    const status = String(job.status ?? '').toUpperCase()
                    const orders = toNumber(result.created_orders, 0)
                    const venuePending = toNumber(((result.order_queue ?? {}) as JsonRecord).pending, 0)
                    const dur = durationSeconds(job)
                    const prog = progressSnapshot(result)
                    return (
                      <button id={`scan-job-${key}`} key={key} type="button"
                        onClick={() => { setSelectedJobId(key); setSelectionMode('manual') }}
                        className={`mb-1 w-full rounded-lg border border-l-2 px-3 py-2.5 text-left transition ${subtleBorder} ${selected ? 'border-l-teal-500 bg-teal-500/8' : darkMode ? 'bg-slate-950/35 hover:bg-slate-800/65' : 'bg-white/60 hover:bg-stone-950/[0.03]'}`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-xs font-semibold text-stone-900">#{String(job.id ?? '--')}</p>
                            <p className="mt-0.5 text-[0.6rem] text-stone-500">{formatRelativeTime(job.created_at)}</p>
                          </div>
                          <div className="text-right">
                            <span className={`inline-block rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wider ${badgeTone(status) === 'good' ? 'bg-teal-500/12 text-teal-800' : badgeTone(status) === 'bad' ? 'bg-rose-500/12 text-rose-700' : badgeTone(status) === 'warn' ? 'bg-amber-500/12 text-amber-800' : 'bg-stone-100 text-stone-500'}`}>{status}</span>
                            <p className="mt-1 text-xs font-bold tabular-nums text-stone-700">{formatNumber(orders, 0)} <span className="text-[0.55rem] font-normal text-stone-500">orders</span></p>
                            {venuePending > 0 ? <p className="mt-0.5 text-[0.55rem] font-semibold uppercase tracking-wider text-amber-700">{formatNumber(venuePending, 0)} venue req pending</p> : null}
                          </div>
                        </div>
                        <p className="mt-1.5 truncate text-[0.68rem] text-stone-500">
                          {symbols.length ? `${symbols[0]}${symbols.length > 1 ? ` +${symbols.length - 1}` : ''}` : '—'}
                        </p>
                        <p className="mt-1 text-[0.6rem] text-stone-500">
                          {Array.isArray(payload.intervals) ? payload.intervals.length : 0}iv · {Array.isArray(payload.modes) ? payload.modes.length : 0}md · {dur !== null ? `${formatNumber(dur, 1)}s` : isActiveStatus(status) ? 'live' : 'err'}
                        </p>
                        {status === 'RUNNING' && prog.totalTasks > 0 ? (
                          <div className="mt-2">
                            <div className="h-1 overflow-hidden rounded-full bg-stone-200">
                              <div className="h-full rounded-full bg-teal-500 transition-[width]" style={{ width: `${prog.percentComplete}%` }} />
                            </div>
                          </div>
                        ) : null}
                      </button>
                    )
                  })}
                </div>
              )) : <p className="p-4 text-xs text-stone-500">No scan jobs matched.</p>}
            </div>
          </aside>

          {/* ── COLUMN 2: SELECTED JOB DETAIL ── */}
          <main className={`flex w-[440px] shrink-0 flex-col overflow-y-auto border-r ${subtleBorder} ${paneBg}`}>
            {selectedJob ? (
              <div className="grid gap-4 p-4">

                {/* identity + toolbar */}
                <div>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Selected Run</p>
                      <div className="mt-1 flex items-center gap-2">
                        <h2 className="text-xl font-bold text-stone-950">Job #{String(selectedJob.id ?? '--')}</h2>
                        <span className={`rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wider ${badgeTone(String(selectedJob.status ?? '')) === 'good' ? 'bg-teal-500/12 text-teal-800' : badgeTone(String(selectedJob.status ?? '')) === 'bad' ? 'bg-rose-500/12 text-rose-700' : badgeTone(String(selectedJob.status ?? '')) === 'warn' ? 'bg-amber-500/12 text-amber-800' : 'bg-stone-100 text-stone-500'}`}>{String(selectedJob.status ?? '--')}</span>
                      </div>
                      <p className="mt-0.5 text-[0.65rem] text-stone-500">{String(selectedJob.run_id ?? '--')}</p>
                      <p className="text-[0.65rem] text-stone-500">{formatTime(selectedJob.started_at)}{selectedJob.finished_at ? ` → ${formatTime(selectedJob.finished_at)}` : ''} · {selectedDuration !== null ? `${formatNumber(selectedDuration, 1)}s` : 'in flight'}</p>
                    </div>
                    {hasActiveScan && (
                      <button type="button" onClick={() => { const aj = jobs.find(j => String(j.run_id ?? '') === activeScanRunId); if (!aj) return; const nid = scanJobKey(aj); setSelectionMode('auto'); setSelectedJobId(nid); queueMicrotask(() => document.getElementById(`scan-job-${nid}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })) }}
                        className="inline-flex items-center gap-1 rounded-lg bg-teal-500/10 px-2.5 py-1.5 text-[0.65rem] font-semibold text-teal-800 hover:bg-teal-500/20">
                        <Radar className="h-3 w-3" strokeWidth={2} /> Follow Active
                      </button>
                    )}
                  </div>

                  {/* control toolbar */}
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <ToolbarBtn icon={Pause} label="Pause" onClick={() => pauseMutation.mutate()} disabled={pauseMutation.isPending || isScanPaused} />
                    <ToolbarBtn icon={Play} label="Resume" onClick={() => resumeMutation.mutate()} disabled={resumeMutation.isPending || (!isScanPaused && !scanControl.stop_requested)} />
                    <ToolbarBtn icon={Square} label="Stop" onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending || !hasActiveScan} danger />
                    <ToolbarBtn icon={Square} label="Stop All" onClick={() => stopAllMutation.mutate()} disabled={stopAllMutation.isPending || !hasActiveScan} danger />
                    <ToolbarBtn icon={OctagonX} label="Force Stop" onClick={() => forceStopAllMutation.mutate()} disabled={forceStopAllMutation.isPending || !hasActiveScan} danger />
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <ToolbarBtn icon={Copy} label="Copy Details" onClick={() => void copyDetails()} />
                    <ToolbarBtn icon={Copy} label="Copy Scope" onClick={() => void copyScope()} />
                    <ToolbarBtn icon={Copy} label="Copy Drill-Down" onClick={() => void copyDrilldownResults()} />
                    <ToolbarBtn icon={Download} label="CSV" onClick={downloadDrilldownCsv} />
                    <ToolbarBtn icon={Download} label="Summary JSON" onClick={downloadScanSummaryJson} />
                  </div>
                </div>

                {/* alerts */}
                {selectedError && <AlertBanner tone="bad" title="Failure reason" message={selectedError} />}
                {selectedDiagnosis && <AlertBanner tone={selectedDiagnosis.tone === 'bad' ? 'bad' : 'warning'} title={selectedDiagnosis.title} message={selectedDiagnosis.message} />}
                {selectedDailyCapWarning && <AlertBanner tone="warning" title="Blocked by daily trade cap" message={`Daily trades: ${formatNumber(selectedDailyCapWarning.dailyTrades, 0)}. Cap-skipped: ${formatNumber(selectedDailyCapWarning.dailyCapSkipped, 0)}.`} />}

                <LiveScanEventPanel
                  latestEvent={liveScanEvents.latestEvent}
                  events={liveScanEvents.events}
                  connectionState={liveScanEvents.connectionState}
                  profileId={liveScanEvents.profileId}
                  runId={liveScanEvents.runId}
                />

                {/* debug block */}
                {(Object.keys(selectedDebug).length > 0 || Boolean(selectedResult.stale_cancelled)) && (
                  <div className={`rounded-xl border p-3 ${darkMode ? 'border-amber-500/25 bg-amber-500/10' : 'border-amber-800/30 bg-amber-950/40'}`}>
                    <SectionHeader icon={CircleAlert} title="Scan debug" />
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      {[['Last reason', String(selectedDebug.last_progress_reason ?? '--')],['Last progress', formatTime(selectedDebug.last_progress_at_utc)],['Pending fetches', formatNumber(selectedDebug.pending_fetch_count, 0)],['Oldest wait', `${formatNumber(selectedDebug.oldest_pending_fetch_age_seconds, 1)}s`]].map(([l, v]) => (
                        <div key={l} className={`rounded-lg px-2.5 py-2 ${darkMode ? 'bg-slate-950/50' : 'bg-white/70'}`}>
                          <p className={`text-[0.6rem] uppercase tracking-wider ${mutedText}`}>{l}</p>
                          <p className={`mt-0.5 font-medium ${darkMode ? 'text-amber-200' : 'text-amber-300'}`}>{v}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* key metrics row */}
                <div className="grid grid-cols-4 gap-2">
                  <MetricTile label="Symbols" value={formatNumber(jobSymbols.length, 0)} />
                  <MetricTile label="Intervals" value={formatNumber(jobIntervals.length, 0)} />
                  <MetricTile label="Orders" value={formatNumber(selectedResult.created_orders, 0)} />
                  <MetricTile label="Duration" value={selectedJob.finished_at ? `${formatNumber(selectedDuration, 1)}s` : '--'} />
                </div>
                {toNumber(((selectedResult.order_queue ?? {}) as JsonRecord).submitted, 0) > 0 ? (
                  <div className="grid grid-cols-4 gap-2">
                    <MetricTile label="Venue req sent" value={formatNumber(((selectedResult.order_queue ?? {}) as JsonRecord).submitted, 0)} />
                    <MetricTile label="Venue pending" value={formatNumber(((selectedResult.order_queue ?? {}) as JsonRecord).pending, 0)} />
                    <MetricTile label="Venue verified" value={formatNumber(((selectedResult.order_queue ?? {}) as JsonRecord).verified, 0)} />
                    <MetricTile label="Need verify" value={formatNumber(((selectedResult.order_queue ?? {}) as JsonRecord).pending_verification, 0)} />
                  </div>
                ) : null}

                {/* progress bar */}
                {String(selectedJob.status ?? '').toUpperCase() === 'RUNNING' && selectedProgress.totalTasks > 0 && (
                  <div className="rounded-xl border border-teal-800/30 bg-teal-950/30 p-3">
                    <div className="flex items-center justify-between text-xs">
                      <span className={`font-semibold ${darkMode ? 'text-teal-300' : 'text-teal-800'}`}>{selectedProgress.completedTasks}/{selectedProgress.totalTasks} tasks</span>
                      <span className={`tabular-nums ${darkMode ? 'text-teal-300' : 'text-teal-700'}`}>{formatNumber(selectedProgress.percentComplete, 0)}%</span>
                    </div>
                    <div className={`mt-2 h-2 overflow-hidden rounded-full ${darkMode ? 'bg-slate-800' : 'bg-stone-200'}`}>
                      <div className="h-full rounded-full bg-teal-500 transition-[width] duration-300" style={{ width: `${selectedProgress.percentComplete}%` }} />
                    </div>
                    {selectedProgress.currentTask && (
                      <p className={`mt-1.5 text-[0.65rem] ${mutedText}`}>{String(selectedProgress.currentTask.symbol ?? '--')} · {String(selectedProgress.currentTask.interval ?? '--')} · {String(selectedProgress.currentTask.mode ?? '--')}</p>
                    )}
                  </div>
                )}

                {/* scan pressure + learning side by side */}
                <div className="grid gap-2">
                  <div className={`rounded-xl p-3 ${softPanelBg}`}>
                    <SectionHeader icon={Clock3} title="Scan pressure" subtitle="Analysis timing, fallbacks, order conversion" />
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      {[['Avg ms', `${formatNumber(selectedAnalysisOverview.analysisAvgMs, 1)}ms`],['p95 ms', `${formatNumber(selectedAnalysisOverview.analysisP95Ms, 1)}ms`],['p99 ms', `${formatNumber(selectedAnalysisOverview.analysisP99Ms, 1)}ms`],['Fallback rate', `${formatNumber(selectedAnalysisOverview.fallbackRatePct, 1)}%`],['Order conv.', `${formatNumber(selectedAnalysisOverview.orderConversionPct, 1)}%`],['Neutral skips', `${formatNumber(selectedAnalysisOverview.neutralSkipPct, 1)}%`]].map(([l, v]) => <MetricTile key={l} label={l} value={v} />)}
                    </div>
                  </div>
                  <div className={`rounded-xl p-3 ${softPanelBg}`}>
                    <SectionHeader icon={Sparkles} title="Learning pressure" subtitle="Emitted signals, confidence suppression" />
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      {[['Signals', formatNumber(selectedLearningOverview.signalCount, 0)],['Raw conf.', `${formatNumber(selectedLearningOverview.avgConfidenceRaw, 1)}%`],['Final conf.', `${formatNumber(selectedLearningOverview.avgConfidenceFinal, 1)}%`],['Δ conf.', `${formatNumber(selectedLearningOverview.avgConfidenceDelta, 1)} pts`],['Comp. pen.', `${formatNumber(selectedLearningOverview.avgComponentPenalty * 100, 2)} pts`],['Entry pen.', `${formatNumber(selectedLearningOverview.avgEntryPenalty * 100, 2)} pts`],['Exec. pen.', `${formatNumber(selectedLearningOverview.avgExecutionPenalty * 100, 2)} pts`],['Learning on', `${selectedLearningOverview.learningActiveCount}/${selectedLearningOverview.signalCount}`]].map(([l, v]) => <MetricTile key={l} label={l} value={v} />)}
                    </div>
                  </div>
                </div>

                {selectedVenueQueueRows.length ? (
                  <div className={`rounded-xl p-3 ${softPanelBg}`}>
                    <SectionHeader icon={Workflow} title="Venue order queue" subtitle="Order requests sent to Binance for this scan" />
                    <div className="mt-3 overflow-hidden rounded-xl border border-stone-900/8">
                      <table className="min-w-full divide-y divide-stone-900/8 text-sm">
                        <thead className="bg-stone-950/[0.03] text-left text-[0.68rem] uppercase tracking-[0.16em] text-stone-500">
                          <tr>
                            <th className="px-3 py-2">Symbol</th>
                            <th className="px-3 py-2">Status</th>
                            <th className="px-3 py-2">Order</th>
                            <th className="px-3 py-2">Venue</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-stone-900/8 bg-white/70">
                          {selectedVenueQueueRows.map((row) => (
                            <tr key={row.id}>
                              <td className="px-3 py-2 text-stone-950">{row.symbol} <span className="text-xs text-stone-500">{row.interval} · {row.mode}</span></td>
                              <td className="px-3 py-2"><StatusBadge label={row.submissionStatus || 'ORDER_REQUEST_SENT'} tone={row.submissionStatus.includes('VERIFIED') || row.submissionStatus === 'SUBMITTED' ? 'good' : row.submissionStatus.includes('PENDING') ? 'warn' : 'neutral'} /></td>
                              <td className="px-3 py-2 text-xs text-stone-600">{row.orderId || '--'}<div>{row.clientOrderId || '--'}</div></td>
                              <td className="px-3 py-2 text-xs text-stone-600">{row.venueOrderId || '--'}<div>{row.orderStatus || '--'}</div></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}

                {/* previous run diff */}
                {selectedPreviousJob && (
                  <div className={`rounded-xl border p-3 ${subtleBorder} ${softPanelBg}`}>
                    <div className="flex items-center justify-between gap-2">
                      <SectionHeader icon={ArrowRight} title="vs previous run" subtitle={`Job #${String(selectedPreviousJob.id ?? '--')} · ${formatTime(selectedPreviousJob.created_at)}`} />
                      <span className={`rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase ${badgeTone(String(selectedPreviousJob.status ?? '')) === 'good' ? 'bg-teal-500/12 text-teal-800' : 'bg-rose-500/12 text-rose-700'}`}>{String(selectedPreviousJob.status ?? '--')}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 xl:grid-cols-3">
                      {[{ label: 'Orders', current: formatNumber(selectedAnalysisOverview.createdOrders, 0), delta: changeText(selectedAnalysisOverview.createdOrders, previousAnalysisOverview.createdOrders, 0) },{ label: 'Signals', current: formatNumber(selectedAnalysisOverview.signalsEmitted, 0), delta: changeText(selectedAnalysisOverview.signalsEmitted, previousAnalysisOverview.signalsEmitted, 0) },{ label: 'Avg ms', current: `${formatNumber(selectedAnalysisOverview.analysisAvgMs, 1)}ms`, delta: changeText(selectedAnalysisOverview.analysisAvgMs, previousAnalysisOverview.analysisAvgMs, 1, 'ms') },{ label: 'Fallback %', current: `${formatNumber(selectedAnalysisOverview.fallbackRatePct, 1)}%`, delta: changeText(selectedAnalysisOverview.fallbackRatePct, previousAnalysisOverview.fallbackRatePct, 1, ' pts') },{ label: 'Conf delta', current: `${formatNumber(selectedLearningOverview.avgConfidenceDelta, 1)} pts`, delta: changeText(selectedLearningOverview.avgConfidenceDelta, previousLearningOverview.avgConfidenceDelta, 1, ' pts') }].map(item => <MetricTile key={item.label} label={item.label} value={item.current} delta={`${item.delta} vs prev`} />)}
                    </div>
                  </div>
                )}

                {/* scope + stage timings */}
                {(Object.keys(selectedScope).length > 0 || selectedStageRows.length > 0) && (
                  <div className="grid gap-2">
                    {Object.keys(selectedScope).length > 0 && (
                      <div className={`rounded-xl p-3 ${softPanelBg}`}>
                        <SectionHeader icon={Workflow} title="Scope efficiency" />
                        <div className="mt-3 grid grid-cols-2 gap-2">
                          {[['Requested tasks', formatNumber(selectedScope.requested_tasks_before_pruning, 0)],['Effective tasks', formatNumber(selectedScope.effective_tasks, 0)],['Fetch tasks', formatNumber(selectedScope.fetch_tasks, 0)],['Active symbols', formatNumber(selectedScope.active_symbols, 0)],['Throttled', formatNumber(selectedScope.throttled_symbols, 0)],['Mode pairs', formatNumber(selectedScope.allowed_mode_pairs, 0)]].map(([l, v]) => <MetricTile key={l} label={l} value={v} />)}
                        </div>
                      </div>
                    )}
                    {selectedStageRows.length > 0 && (
                      <div className={`rounded-xl p-3 ${softPanelBg}`}>
                        <SectionHeader icon={Clock3} title="Stage timings" />
                        <div className="mt-3 grid gap-2">
                          {selectedStageRows.map(row => (
                            <div key={row.key} className={`flex items-center justify-between rounded-lg px-3 py-2 ${darkMode ? 'bg-slate-950/55' : 'bg-white/70'}`}>
                              <span className={`text-xs font-medium ${subtleText}`}>{row.label}</span>
                              <div className="text-right">
                                <p className={`text-xs font-semibold tabular-nums ${strongText}`}>{formatNumber(row.stats.avg_ms, 2)}ms avg</p>
                                <p className={`text-[0.6rem] ${mutedText}`}>{formatNumber(row.stats.count, 0)} calls · p95 {formatNumber(row.stats.p95_ms ?? row.stats.max_ms, 2)}ms</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* scan scope symbols */}
                <div className="rounded-xl bg-stone-950/[0.03] p-3">
                  <SectionHeader icon={Workflow} title="Scan scope" />
                  <div className="mt-3 grid gap-3">
                    <div>
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <p className="text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Symbols</p>
                        {jobSymbols.length > 18 ? (
                          <button
                            type="button"
                            onClick={() => setShowAllSymbols((current) => !current)}
                            className="inline-flex items-center gap-1 rounded-full border border-stone-900/8 bg-white px-2.5 py-1 text-[0.6rem] font-semibold text-stone-700 transition hover:bg-stone-950/[0.03]"
                          >
                            {showAllSymbols ? 'Show less' : `Show all ${formatNumber(jobSymbols.length, 0)}`}
                            {showAllSymbols ? <ChevronUp className="h-3 w-3" strokeWidth={1.8} /> : <ChevronDown className="h-3 w-3" strokeWidth={1.8} />}
                          </button>
                        ) : null}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {jobSymbols.length ? (showAllSymbols ? jobSymbols : jobSymbols.slice(0, 18)).map((s, i) => (
                          <div key={`${s}-${i}`} className="flex items-center gap-0.5 rounded-md border border-stone-900/8 bg-white px-1.5 py-1">
                            <Link to={`/markets?symbol=${encodeURIComponent(s)}`} className="text-xs font-semibold text-stone-700">{s}</Link>
                            <Link to={`/markets?symbol=${encodeURIComponent(s)}&analyze=1`} className="ml-1 rounded px-1 py-0.5 text-[0.55rem] font-bold bg-teal-500/10 text-teal-800">↗</Link>
                          </div>
                        )) : <span className="text-xs text-stone-500">No symbols captured.</span>}
                      </div>
                      {!showAllSymbols && jobSymbols.length > 18 ? <p className="mt-2 text-[0.65rem] text-stone-500">Showing 18 of {formatNumber(jobSymbols.length, 0)} symbols.</p> : null}
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div><p className="text-[0.6rem] uppercase tracking-widest text-stone-500">Intervals</p><p className="mt-1 text-stone-700">{jobIntervals.join(', ') || '--'}</p></div>
                      <div><p className="text-[0.6rem] uppercase tracking-widest text-stone-500">Modes</p><p className="mt-1 text-stone-700">{jobModes.join(', ') || '--'}</p></div>
                    </div>
                  </div>
                </div>

              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center p-8">
                <EmptyState message="Select a scan job to inspect its scope and engine result." />
              </div>
            )}
          </main>

          {/* ── COLUMN 3: DRILL-DOWN ── */}
          <section className={`flex flex-1 flex-col overflow-y-auto ${paneBg}`}>
            {selectedJob ? (
              <div className="grid gap-4 p-4">

                {/* header + search */}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <SectionHeader icon={Sparkles} title="Per-symbol drill-down" subtitle="Signals + traced skip decisions with confidence path" />
                  <label className="relative flex items-center">
                    <Search className="pointer-events-none absolute left-3 h-3.5 w-3.5 text-stone-400" strokeWidth={1.8} />
                    <input value={detailQuery} onChange={e => setDetailQuery(e.target.value)} placeholder="Filter symbols, modes…"
                      className="h-8 w-64 rounded-lg border border-stone-900/8 bg-white pl-9 pr-3 text-xs text-stone-900 outline-none placeholder:text-stone-400 focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
                    />
                  </label>
                </div>

                {/* skip breakdown */}
                <div className="rounded-xl bg-stone-950/[0.03] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <SectionHeader icon={Workflow} title="Skip breakdown" subtitle={`${formatNumber(skipTotal, 0)} total skipped`} />
                    <span className="text-xs tabular-nums text-stone-500">{formatNumber(selectedSkipTraceRows.length, 0)} traced</span>
                  </div>
                  {skipRows.length ? (
                    <div className="mt-3 grid gap-3">
                      <SkipBar rows={skipRows} toneForKey={skipTone} />
                      <div className="grid grid-cols-2 gap-3">
                        {skipRows.map(r => (
                          <div key={r.key} className="flex items-center justify-between text-xs">
                            <div className="flex items-center gap-1.5"><span className={`h-2 w-2 rounded-sm ${skipTone(r.key)}`} /><span className="text-stone-600">{r.key.replaceAll('_', ' ')}</span></div>
                            <span className="tabular-nums text-stone-500">{formatNumber(r.count, 0)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : <p className="mt-3 text-xs text-stone-500">No skip summary was recorded for this job.</p>}
                </div>

                {/* skip attribution */}
                <div className="rounded-xl bg-stone-950/[0.03] p-4">
                  <SectionHeader icon={Workflow} title="Skip attribution" subtitle="Traced skips by stage and reason code, split into directional skips vs engine neutrals" />
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    {[
                      ['Traced', formatNumber(selectedSkipTraceRows.length, 0)],
                      ['Directional', formatNumber(selectedSkipConfidenceStats.directional.count, 0)],
                      ['Neutral', formatNumber(selectedSkipConfidenceStats.neutral.count, 0)],
                      ['Dir raw conf.', selectedSkipConfidenceStats.directional.withConfidenceCount ? `${formatNumber(selectedSkipConfidenceStats.directional.avgRaw, 1)}%` : '--'],
                      ['Dir final conf.', selectedSkipConfidenceStats.directional.withConfidenceCount ? `${formatNumber(selectedSkipConfidenceStats.directional.avgFinal, 1)}%` : '--'],
                      ['Neutral final', selectedSkipConfidenceStats.neutral.withConfidenceCount ? `${formatNumber(selectedSkipConfidenceStats.neutral.avgFinal, 1)}%` : '--'],
                    ].map(([l, v]) => <MetricTile key={l} label={l} value={v} />)}
                  </div>
                  {selectedSkipConfidenceStats.neutral.count > selectedSkipConfidenceStats.directional.count && (
                    <div className="mt-4">
                      <AlertBanner
                        tone="warning"
                        title="Engine neutrals dominate this run"
                        message="Most traced skips in this job are engine-side NEUTRAL / NO_TRADE outcomes. Directional skip confidence and neutral no-trade confidence are different semantics, so the tiles above separate them explicitly."
                      />
                    </div>
                  )}
                  <div className="mt-4 grid gap-4 xl:grid-cols-2">
                    <div><p className="mb-2 text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">By stage</p>{selectedSkipStageBreakdown.length ? <BreakdownList rows={selectedSkipStageBreakdown} color="bg-teal-500" /> : <p className="text-xs text-stone-500">No skip traces captured.</p>}</div>
                    <div><p className="mb-2 text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">By reason code</p>{selectedSkipReasonBreakdown.length ? <BreakdownList rows={selectedSkipReasonBreakdown} color="bg-stone-500" /> : <p className="text-xs text-stone-500">No reason-code attribution captured.</p>}</div>
                  </div>
                </div>

                {/* decision table */}
                <div className={`overflow-hidden rounded-xl border ${subtleBorder} ${tableFrameBg}`}>
                  <div className={`border-b px-4 py-3 ${subtleBorder} ${tableHeadBg}`}>
                    <SectionHeader icon={Sparkles} title="Decision rows" subtitle={`${sortedDecisionRows.length} signals + skips`} />
                  </div>
                  {sortedDecisionRows.length ? (
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-stone-900/8 text-xs">
                        <thead className={tableHeadBgSoft}>
                          <tr className="text-left">
                            {([
                              ['type', 'Type'],
                              ['symbol', 'Symbol'],
                              ['interval', 'Intv'],
                              ['mode', 'Mode'],
                              ['direction', 'Dir'],
                              ['confidence', 'Confidence'],
                              ['learning', 'Learning'],
                              ['outcome', 'Outcome'],
                              ['summary', 'Summary'],
                            ] as [DecisionSortKey, string][]).map(([key, label]) => (
                              <th key={key} className="whitespace-nowrap px-3 py-2.5 text-[0.6rem] font-semibold uppercase tracking-widest">
                                <SortHeader
                                  label={label}
                                  active={decisionSortKey === key}
                                  descending={decisionSortDescending}
                                  onClick={() => {
                                    if (decisionSortKey === key) setDecisionSortDescending((current) => !current)
                                    else {
                                      setDecisionSortKey(key)
                                      setDecisionSortDescending(key === 'confidence')
                                    }
                                  }}
                                />
                              </th>
                            ))}
                            <th className="whitespace-nowrap px-3 py-2.5 text-[0.6rem] font-semibold uppercase tracking-widest text-stone-500">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-stone-900/8">
                          {sortedDecisionRows.map(row => (
                            <tr key={row.id} className={`align-top ${darkMode ? 'hover:bg-slate-800/60' : 'hover:bg-stone-950/[0.03]'}`}>
                              <td className="px-3 py-2.5">
                                <span className={`inline-flex rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wider ${row.detailType === 'SIGNAL' ? 'bg-teal-500/12 text-teal-800' : 'bg-amber-500/12 text-amber-800'}`}>{row.detailType}</span>
                              </td>
                              <td className="px-3 py-2.5 font-semibold text-stone-900">{row.symbol}</td>
                              <td className="px-3 py-2.5 text-stone-500">{row.interval}</td>
                              <td className="px-3 py-2.5 text-stone-500">{row.mode}</td>
                              <td className="px-3 py-2.5">
                                <span className={`rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase ${row.direction.toUpperCase() === 'BUY' ? 'bg-teal-500/12 text-teal-800' : row.direction.toUpperCase() === 'SELL' ? 'bg-rose-500/12 text-rose-700' : 'bg-stone-100 text-stone-500'}`}>{row.direction}</span>
                              </td>
                              <td className="px-3 py-2.5">
                                <p className="font-semibold tabular-nums text-stone-900">{row.confidenceFinal != null ? `${formatNumber(row.confidenceFinal, 1)}%` : '--'}</p>
                                <p className="text-[0.6rem] text-stone-500">raw {row.confidenceRaw != null ? `${formatNumber(row.confidenceRaw, 1)}%` : '--'} · {row.confidenceDelta != null ? `${formatNumber(row.confidenceDelta, 1)}pts` : '--'}</p>
                              </td>
                              <td className="px-3 py-2.5">
                                <p className="font-medium text-stone-700">{row.learningLabel}</p>
                                <p className="text-[0.6rem] text-stone-500">{row.learningDetail}</p>
                              </td>
                              <td className="px-3 py-2.5 text-stone-600">{row.outcome}</td>
                              <td className="max-w-xs px-3 py-2.5 text-stone-500">{row.summary}</td>
                              <td className="px-3 py-2.5">
                                <div className="flex flex-wrap gap-2">
                                  <Link
                                    to={`/markets?symbol=${encodeURIComponent(row.symbol)}&analyze=1&profile=${encodeURIComponent(profileScope)}`}
                                    className="inline-flex items-center gap-1 rounded-md border border-stone-900/8 bg-white px-2 py-1 text-[0.65rem] font-semibold text-stone-600 transition hover:text-stone-900"
                                  >
                                    <Radar className="h-3.5 w-3.5" strokeWidth={1.8} />
                                    Analyze
                                  </Link>
                                  {row.detailType === 'SIGNAL' && (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        navigate(`/trade/manual-order?profile=${encodeURIComponent(profileScope)}`, { state: { signal: row.rawRecord } })
                                      }}
                                      className="inline-flex items-center gap-1 rounded-md border border-teal-500/20 bg-teal-500/10 px-2 py-1 text-[0.65rem] font-semibold text-teal-800 transition hover:bg-teal-500/15 disabled:pointer-events-none disabled:opacity-50"
                                    >
                                      <Play className="h-3.5 w-3.5" strokeWidth={1.8} />
                                      Create trade
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="p-5">
                      <p className="text-xs font-semibold text-stone-600">No per-symbol confidence traces captured for this run.</p>
                      <p className="mt-1.5 text-xs leading-relaxed text-stone-500">Once the runtime records emitted signals or traced skip decisions, raw/final confidence will appear here.</p>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {jobSymbols.slice(0, 12).map((s, i) => <Link key={`${s}-${i}`} to={`/markets?symbol=${encodeURIComponent(s)}&analyze=1`} className="rounded-md border border-stone-900/8 bg-white px-2 py-1 text-[0.65rem] font-semibold text-stone-600 hover:text-stone-900">{s}</Link>)}
                      </div>
                    </div>
                  )}
                </div>

                {/* skip trace table */}
                {sortedSkipTraceRows.length > 0 && (
                  <div className={`overflow-hidden rounded-xl border ${subtleBorder} ${tableFrameBg}`}>
                    <div className={`border-b px-4 py-3 ${subtleBorder} ${tableHeadBg}`}>
                      <SectionHeader icon={Workflow} title="Skip trace detail" subtitle={`Top ${Math.min(40, sortedSkipTraceRows.length)} of ${sortedSkipTraceRows.length}`} />
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-stone-900/8 text-xs">
                        <thead className={tableHeadBgSoft}>
                          <tr className="text-left">
                            {([
                              ['symbol', 'Symbol'],
                              ['mode', 'Mode'],
                              ['stage', 'Stage'],
                              ['reason', 'Reason'],
                              ['confidence', 'Confidence path'],
                              ['suppression', 'Suppression'],
                            ] as [SkipTraceSortKey, string][]).map(([key, label]) => (
                              <th key={key} className="whitespace-nowrap px-3 py-2.5 text-[0.6rem] font-semibold uppercase tracking-widest">
                                <SortHeader
                                  label={label}
                                  active={skipTraceSortKey === key}
                                  descending={skipTraceSortDescending}
                                  onClick={() => {
                                    if (skipTraceSortKey === key) setSkipTraceSortDescending((current) => !current)
                                    else {
                                      setSkipTraceSortKey(key)
                                      setSkipTraceSortDescending(key === 'confidence' || key === 'suppression')
                                    }
                                  }}
                                />
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-stone-900/8">
                          {sortedSkipTraceRows.slice(0, 40).map(row => (
                            <tr key={row.traceId || `${row.symbol}-${row.timestamp}-${row.stage}`} className={`align-top ${darkMode ? 'hover:bg-slate-800/60' : 'hover:bg-stone-950/[0.03]'}`}>
                              <td className="px-3 py-2.5"><p className="font-semibold text-stone-900">{row.symbol}</p><p className="text-[0.6rem] text-stone-500">{row.interval} · {formatTime(row.timestamp)}</p></td>
                              <td className="px-3 py-2.5 text-stone-500">{row.mode}</td>
                              <td className="px-3 py-2.5 text-stone-600">{row.stage.replaceAll('_', ' ')}</td>
                              <td className="px-3 py-2.5"><p className="font-medium text-stone-700">{row.reasonCode.replaceAll('_', ' ')}</p><p className="text-[0.6rem] text-stone-500">{row.noTradeReason !== '--' ? row.noTradeReason : row.reasonText}</p></td>
                              <td className="px-3 py-2.5">
                                {row.confidenceRaw != null && row.confidenceFinal != null ? (
                                  <><p className="font-semibold tabular-nums text-stone-900">{formatNumber(row.confidenceRaw, 1)}% → {formatNumber(row.confidenceFinal, 1)}%</p><p className="text-[0.6rem] text-stone-500">{formatNumber(row.confidenceDelta ?? 0, 1)} pts · q {row.qualityMultiplier != null ? `×${formatNumber(row.qualityMultiplier, 3)}` : '--'}</p></>
                                ) : <span className="text-stone-500">—</span>}
                              </td>
                              <td className="px-3 py-2.5 tabular-nums text-stone-600">{row.learningPenaltyPts != null ? `${formatNumber(row.learningPenaltyPts, 2)} pts` : '--'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center p-8">
                <EmptyState message="Select a scan job to inspect per-symbol signal output." />
              </div>
            )}
          </section>
        </div>

        {/* ── SCAN BUILDER (collapsible) ── */}
        <div className={`mt-4 rounded-[1.8rem] border shadow-[0_18px_40px_rgba(77,62,40,0.08)] ${subtleBorder} ${cardBg}`}>
          <button type="button" onClick={() => setBuilderOpen(o => !o)}
            className={`flex w-full items-center justify-between px-6 py-3 text-left ${darkMode ? 'hover:bg-slate-800/70' : 'hover:bg-stone-950/[0.03]'}`}
          >
            <div className="flex items-center gap-2.5">
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-teal-500/10">
                <Sparkles className="h-3 w-3 text-teal-600" strokeWidth={1.8} />
              </span>
              <span className={`text-xs font-semibold ${strongText}`}>Custom Scan Builder</span>
              <span className={`text-xs ${mutedText}`}>Start a selective ad-hoc scan</span>
            </div>
            <div className="flex items-center gap-3">
              <Link to="/operations/admin" onClick={e => e.stopPropagation()} className={`text-xs ${mutedText} ${darkMode ? 'hover:text-slate-200' : 'hover:text-stone-900'}`}>Open standalone admin →</Link>
              {builderOpen ? <ChevronUp className={`h-3.5 w-3.5 ${mutedText}`} strokeWidth={1.8} /> : <ChevronDown className={`h-3.5 w-3.5 ${mutedText}`} strokeWidth={1.8} />}
            </div>
          </button>
          {builderOpen && (
            <div className={`border-t px-6 py-5 ${subtleBorder}`}>
              <ScanJobForm
                onSubmit={payload => queueMutation.mutate(payload)}
                isSubmitting={queueMutation.isPending}
                availableSymbols={availableSymbols}
                availableIntervals={availableIntervals}
                availableModes={availableModes}
                defaultModes={enabledModes.length ? enabledModes : availableModes.slice(0, 2)}
                modeIntervalPolicy={modeIntervalPolicy}
              />
            </div>
          )}
        </div>

      </div>
    </AnimatedRoute>
  )
}