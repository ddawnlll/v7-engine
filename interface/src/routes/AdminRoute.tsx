import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  Circle,
  Radar,
  RefreshCw,
  ScanSearch,
  Settings2,
  Pause,
  Play,
  Square,
  TimerReset,
  Workflow,
  XCircle,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'

import { ScanJobForm } from '../components/forms/ScanJobForm'
import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useProfileScopeOptions } from '../hooks/useProfileScopeOptions'
import { useQueueScanMutation } from '../hooks/useQueueScanMutation'
import { useRetryFailedJobsMutation } from '../hooks/useRetryFailedJobsMutation'
import { useUpdateRuntimeSettingsMutation } from '../hooks/useUpdateRuntimeSettingsMutation'
import { depositPaperBalance, exportLearningCsv, fetchCalibrationStatus, fetchEngineHealth, fetchJobs, fetchLogs, fetchOperatorAlerts, fetchPaperBalance, fetchRuntimeSettings, fetchSymbols, getCircuitBreakerEvents, getCircuitBreakerState, getFailures, getFailureSummary, getLearningEffectiveness, getLearningProfile, getWeaknessProfile, pauseScans, reconcilePaperBalance, resetCircuitBreaker, resetPaperBalance, resumeScans, stopScans, triggerScanNow, updateCircuitBreakerSettings, fetchV5Overview, fetchV5Models, fetchV5Comparison, fetchV5Readiness, promoteV5, rollbackV5, fetchV5GateReport, fetchV5GateCalibration } from '../lib/api'
import { downloadFile, exportFilename } from '../lib/export'
import { formatNumber, formatTime, statusTone, toNumber } from '../lib/format'
import { DEFAULT_PROFILE_SCOPE, normalizeProfileScope, profileScopeToApiProfileId } from '../lib/profileScope'
import { queryClient } from '../lib/queryClient'
import type {
  CalibrationScopeRow,
  CircuitBreakerEvent,
  CircuitBreakerState,
  FailureRecord,
  FailureSummaryPayload,
  JobItem,
  JobQueueSnapshot,
  LearningEffectivenessPayload,
  LearningProfilePayload,
  LogEntry,
  OperatorAlertRow,
  PaperAccountPayload,
  RuntimeSettingsPayload,
  ScanControlState,
  WeaknessProfilePayload,
} from '../lib/types'

type AdminTab = 'overview' | 'queue' | 'intelligence' | 'budget' | 'settings' | 'alerts'
type AdminRouteProps = {
  initialTab?: AdminTab
  lockedTab?: AdminTab | null
  visibleTabs?: AdminTab[]
  hideTabBar?: boolean
}

const STRATEGY_MODE_CATALOG = [
  {
    value: 'SCALP',
    label: 'Scalp',
    description: 'Fast mean-reversion and micro-breakout setups.',
    recommendedIntervals: ['15m', '30m', '1h', '4h'],
  },
  {
    value: 'SWING',
    label: 'Swing',
    description: 'Higher-conviction directional holds over longer windows.',
    recommendedIntervals: ['1h', '4h', '1d', '3d', '7d'],
  },
  {
    value: 'AGGRESSIVE_SCALP',
    label: 'Aggressive scalp',
    description: 'High-velocity execution with tighter timing requirements.',
    recommendedIntervals: ['15m', '1h', '4h'],
  },
] as const

const INTERVAL_OPTION_CATALOG = ['15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '3d', '7d', '14d', '1M'] as const
const LEARNING_PRESETS = [
  {
    id: 'disabled',
    label: 'Learning Disabled',
    description: 'Turns off learning adjustments entirely. Calibration and adaptive stop remain off.',
    values: {
      LEARNING_ENGINE_ENABLED: 'false',
      LEARNING_CALIBRATION_ENABLED: 'false',
      LEARNING_ADAPTIVE_STOP_ENABLED: 'false',
    },
  },
  {
    id: 'safe',
    label: 'Learning Enabled',
    description: 'Keeps the learning engine on, but leaves calibration and adaptive stop disabled.',
    values: {
      LEARNING_ENGINE_ENABLED: 'true',
      LEARNING_CALIBRATION_ENABLED: 'false',
      LEARNING_ADAPTIVE_STOP_ENABLED: 'false',
    },
  },
  {
    id: 'experimental',
    label: 'Experimental Learning',
    description: 'Enables calibration and adaptive stop in addition to the learning engine. Use only for explicit testing.',
    values: {
      LEARNING_ENGINE_ENABLED: 'true',
      LEARNING_CALIBRATION_ENABLED: 'true',
      LEARNING_ADAPTIVE_STOP_ENABLED: 'true',
    },
  },
] as const

function modeIntervalSettingKey(mode: string) {
  return `AUTONOMOUS_INTERVALS_${String(mode).toUpperCase()}`
}

function severityClasses(kind: string) {
  const normalized = kind.toLowerCase()
  if (normalized.includes('error') || normalized.includes('fail') || normalized.includes('critical')) {
    return 'border-rose-900/10 bg-rose-50/90 text-rose-900'
  }
  if (normalized.includes('complete') || normalized.includes('success')) {
    return 'border-teal-900/10 bg-teal-50/90 text-teal-900'
  }
  if (normalized.includes('warn') || normalized.includes('running')) {
    return 'border-amber-900/10 bg-amber-50/90 text-amber-900'
  }
  return 'border-stone-900/8 bg-white/90 text-stone-800'
}

function groupSettings(settings: Record<string, string>) {
  const groups = {
    Risk: [] as [string, string][],
    Execution: [] as [string, string][],
    Filters: [] as [string, string][],
    Engine: [] as [string, string][],
  }

  for (const entry of Object.entries(settings)) {
    const [key] = entry
    const normalized = key.toLowerCase()
    if (normalized.includes('risk') || normalized.includes('loss') || normalized.includes('drawdown')) {
      groups.Risk.push(entry)
    } else if (normalized.includes('open') || normalized.includes('worker') || normalized.includes('interval') || normalized.includes('scan')) {
      groups.Execution.push(entry)
    } else if (normalized.includes('confidence') || normalized.includes('volume') || normalized.includes('mode') || normalized.includes('filter') || normalized.includes('symbol')) {
      groups.Filters.push(entry)
    } else {
      groups.Engine.push(entry)
    }
  }

  return groups
}

function prettySettingLabel(key: string) {
  return key.replaceAll('_', ' ').replace(/\b\w/g, (match) => match.toUpperCase())
}

function settingTone(key: string, value: string) {
  const normalizedKey = key.toLowerCase()
  const numericValue = Number(value)
  if (normalizedKey.includes('loss') && Number.isFinite(numericValue) && numericValue <= 1) return 'text-rose-800'
  if (normalizedKey.includes('risk') && Number.isFinite(numericValue) && numericValue > 2) return 'text-amber-900'
  return 'text-teal-900'
}

function settingHint(key: string) {
  const normalizedKey = key.toLowerCase()
  if (normalizedKey.includes('circuit_breaker_enabled')) return 'Enable or disable the autonomous safety gate entirely.'
  if (normalizedKey.includes('circuit_breaker_manual_mode')) return 'AUTO evaluates recent trade damage. FORCE_OPEN blocks autonomous scans. FORCE_CLOSED bypasses breaker trips.'
  if (normalizedKey.includes('circuit_breaker_lookback')) return 'How many recent closed trades the breaker uses for failure-rate evaluation.'
  if (normalizedKey.includes('circuit_breaker_max_consecutive_losses')) return 'Trip OPEN when the recent uninterrupted loss streak reaches this number.'
  if (normalizedKey.includes('circuit_breaker_max_failure_rate_pct')) return 'Trip OPEN when recent losing-trade percentage reaches this threshold.'
  if (normalizedKey.includes('circuit_breaker_max_severity_avg')) return 'Trip OPEN when recent classified loss severity becomes too high.'
  if (normalizedKey.includes('circuit_breaker_cooldown_minutes')) return 'How long autonomous scans stay paused after an OPEN trip.'
  if (normalizedKey.includes('circuit_breaker_degraded_multiplier')) return 'Confidence multiplier applied while the breaker is DEGRADED.'
  if (normalizedKey.includes('symbol_throttle_enabled')) return 'Suppress symbols with repeated stop-hit damage before they keep consuming scan budget.'
  if (normalizedKey.includes('symbol_throttle_lookback_trades')) return 'How many recent closed trades per symbol are evaluated for tactical suppression.'
  if (normalizedKey.includes('symbol_throttle_max_consecutive_stop_hits')) return 'Throttle when a symbol records this many stop hits in a row.'
  if (normalizedKey.includes('symbol_throttle_max_stop_hit_rate_pct')) return 'Throttle when recent stop-hit percentage breaches this threshold.'
  if (normalizedKey.includes('symbol_throttle_cooldown_minutes')) return 'How long a throttled symbol stays suppressed after the latest triggering stop hit.'
  if (normalizedKey.includes('symbol_throttle_seeded_symbols')) return 'Temporary seeded guardrails for repeat offenders from the diagnostic report.'
  if (normalizedKey.includes('learning_engine_enabled')) return 'Master switch for learning-driven execution penalties and adjustments.'
  if (normalizedKey.includes('learning_calibration_enabled')) return 'Enables confidence calibration. This is disabled by default because it still needs validation.'
  if (normalizedKey.includes('learning_adaptive_stop_enabled')) return 'Allows the learning layer to widen stops. This is disabled by default.'
  if (normalizedKey.includes('v6_actionability_confidence_enabled')) return 'When disabled, scans use the v6 selected-head probability instead of the stricter final actionability confidence.'
  if (normalizedKey.includes('learning_lookback_days')) return 'How much closed-trade history the learning profile reads.'
  if (normalizedKey.includes('learning_min_confidence')) return 'Minimum confidence threshold for failures included in learning analysis.'
  if (normalizedKey.includes('learning_refresh_seconds')) return 'How often the background learning profile refresh runs.'
  if (normalizedKey.includes('paper_default_balance')) return 'Default cash used when the paper account is created or reset.'
  if (normalizedKey.includes('paper_position_size_min_pct')) return 'Minimum percent of available paper cash allocated to a qualifying trade.'
  if (normalizedKey.includes('paper_position_size_max_pct')) return 'Maximum percent of available paper cash allocated to the strongest trade.'
  if (normalizedKey.includes('paper_position_confidence_floor')) return 'Confidence level that maps to the minimum allocation.'
  if (normalizedKey.includes('paper_position_confidence_ceil')) return 'Confidence level that maps to the maximum allocation.'
  if (normalizedKey.includes('autonomous_intervals_aggressive_scalp')) return 'Allowed intervals when aggressive scalp is selected.'
  if (normalizedKey.includes('autonomous_intervals_scalp')) return 'Allowed intervals when scalp is selected.'
  if (normalizedKey.includes('autonomous_intervals_swing')) return 'Allowed intervals when swing is selected.'
  if (normalizedKey.includes('autonomous_allowed_trade_directions')) return 'Choose whether runtime may open long trades, short trades, or both. Opposite-side signals are skipped with an explicit runtime reason.'
  if (normalizedKey.includes('risk')) return 'Per-trade exposure control.'
  if (normalizedKey.includes('loss')) return 'Daily safety stop for the engine.'
  if (normalizedKey.includes('scan') || normalizedKey.includes('interval')) return 'Cadence and throughput for scanning.'
  if (normalizedKey.includes('worker')) return 'Parallel scan capacity.'
  if (normalizedKey.includes('confidence')) return 'Minimum threshold before signals qualify.'
  if (normalizedKey.includes('mode')) return 'Which strategy families are allowed.'
  if (normalizedKey.includes('symbol')) return 'Universe included in manual and autonomous scans.'
  return 'Current runtime configuration value.'
}

function splitCsv(value: string | undefined) {
  return String(value ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function preferLargerSymbolUniverse(primary: string[] | undefined, fallback: string[]) {
  const primaryList = Array.isArray(primary) ? primary.map((item) => String(item)) : []
  return primaryList.length >= fallback.length ? primaryList : fallback
}

function normalizeBooleanSetting(value: string | undefined) {
  return ['1', 'true', 'yes', 'on'].includes(String(value ?? '').toLowerCase()) ? 'true' : 'false'
}

function compactLogMessage(item: LogEntry) {
  return String(item.message ?? item.symbol ?? item.category ?? 'System event')
}

function alertToneClasses(severity: string) {
  const normalized = severity.toLowerCase()
  if (normalized === 'critical') return 'border-rose-900/10 bg-rose-50/90 text-rose-900'
  if (normalized === 'warning') return 'border-amber-900/10 bg-amber-50/90 text-amber-900'
  return 'border-stone-900/8 bg-white text-stone-800'
}

function summarizeAlertsBySeverity(items: OperatorAlertRow[]) {
  return [
    ['Critical', items.filter((item) => String(item.severity ?? '').toLowerCase() === 'critical').length],
    ['Warning', items.filter((item) => String(item.severity ?? '').toLowerCase() === 'warning').length],
    ['Info', items.filter((item) => String(item.severity ?? '').toLowerCase() === 'info').length],
  ] as const
}

function summarizeAlertsByScope(items: OperatorAlertRow[]) {
  const counts = new Map<string, number>()
  for (const item of items) {
    const scope = String(item.scope ?? 'runtime')
    counts.set(scope, (counts.get(scope) ?? 0) + 1)
  }
  return Array.from(counts.entries()).slice(0, 6)
}

function latestCompletedScan(items: JobItem[]) {
  return items.find((item) => String(item.status ?? '').toUpperCase() === 'COMPLETED')
}

function firstCriticalMessage(alerts: OperatorAlertRow[], logs: LogEntry[]) {
  const alert = alerts.find((item) => String(item.severity ?? '').toLowerCase() === 'critical')
  if (alert?.message) return String(alert.message)
  const log = logs.find((item) => String(item.severity ?? '').toLowerCase().includes('error'))
  return String(log?.message ?? '').trim()
}

function computeSizingPreview(confidence: number, availableCash: number, settings: Record<string, string>) {
  const minPct = Math.max(0, Number(settings.PAPER_POSITION_SIZE_MIN_PCT ?? 2))
  const maxPct = Math.max(minPct, Number(settings.PAPER_POSITION_SIZE_MAX_PCT ?? 12))
  const floor = Number(settings.PAPER_POSITION_CONFIDENCE_FLOOR ?? 60)
  const ceil = Math.max(floor, Number(settings.PAPER_POSITION_CONFIDENCE_CEIL ?? 90))
  const normalized = ceil <= floor ? (confidence >= ceil ? 1 : 0) : Math.max(0, Math.min(1, (confidence - floor) / (ceil - floor)))
  const allocationPct = minPct + (maxPct - minPct) * normalized
  return {
    allocationPct,
    notional: availableCash * (allocationPct / 100),
  }
}

function latestDailyCapBlock(job: JobItem | undefined | null) {
  const result = ((job?.result ?? {}) as Record<string, unknown>)
  const skipped = ((result.skipped ?? {}) as Record<string, unknown>)
  const createdOrders = toNumber(result.created_orders, 0)
  const capReached = Boolean(result.cap_reached)
  const dailyCapSkipped = toNumber(skipped.daily_cap_reached, 0)
  if (createdOrders > 0) return null
  if (!capReached && dailyCapSkipped <= 0) return null
  return {
    runId: String(job?.run_id ?? '--'),
    dailyTrades: toNumber(result.daily_trades, 0),
    dailyCapSkipped,
  }
}

function topEntries(counts: Record<string, number> | undefined, limit = 5) {
  return Object.entries(counts ?? {})
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit)
}

export function AdminRoute({
  initialTab = 'overview',
  lockedTab = null,
  visibleTabs,
  hideTabBar = false,
}: AdminRouteProps = {}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const { options: profileScopeOptions } = useProfileScopeOptions()
  const circuitProfileScope = normalizeProfileScope(searchParams.get('profile'), profileScopeOptions)
  const circuitProfileId = profileScopeToApiProfileId(circuitProfileScope, profileScopeOptions) ?? DEFAULT_PROFILE_SCOPE
  const [activeTab, setActiveTab] = useState<AdminTab>(lockedTab ?? initialTab)
  const [jobFilter, setJobFilter] = useState('')
  const healthQuery = useQuery({
    queryKey: ['engine-health'],
    queryFn: fetchEngineHealth,
    refetchInterval: 10_000,
    refetchOnWindowFocus: false,
  })
  const jobsQuery = useQuery({
    queryKey: ['scan-jobs', 'admin'],
    queryFn: () => fetchJobs(200),
    refetchInterval: 10_000,
    refetchOnWindowFocus: false,
  })
  const logsQuery = useQuery({
    queryKey: ['engine-logs', 'admin'],
    queryFn: () => fetchLogs(16, 'ALL'),
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const alertsQuery = useQuery({
    queryKey: ['operator-alerts', 'admin'],
    queryFn: fetchOperatorAlerts,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const settingsQuery = useQuery({
    queryKey: ['runtime-settings'],
    queryFn: fetchRuntimeSettings,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const paperBalanceQuery = useQuery({
    queryKey: ['paper-balance'],
    queryFn: fetchPaperBalance,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const calibrationQuery = useQuery({
    queryKey: ['calibration-status'],
    queryFn: () => fetchCalibrationStatus(5000),
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  
  const v5OverviewQuery = useQuery({
    queryKey: ['v5-overview'],
    queryFn: fetchV5Overview,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const v5ModelsQuery = useQuery({
    queryKey: ['v5-models'],
    queryFn: fetchV5Models,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const v5ComparisonQuery = useQuery({
    queryKey: ['v5-comparison'],
    queryFn: fetchV5Comparison,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const v5ReadinessQuery = useQuery({
    queryKey: ['v5-readiness'],
    queryFn: fetchV5Readiness,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const v5GateReportQuery = useQuery({
    queryKey: ['v5-gate-report'],
    queryFn: fetchV5GateReport,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const symbolsQuery = useQuery({
    queryKey: ['symbols', 'admin'],
    queryFn: fetchSymbols,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const failuresQuery = useQuery({
    queryKey: ['failures', 'admin'],
    queryFn: () => getFailures({ limit: 500 }),
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const failureSummaryQuery = useQuery({
    queryKey: ['failure-summary', 'admin'],
    queryFn: () => getFailureSummary(),
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const weaknessQuery = useQuery({
    queryKey: ['weakness-profile', 'admin'],
    queryFn: () => getWeaknessProfile(30, 0.6),
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const learningQuery = useQuery({
    queryKey: ['learning-profile', 'admin'],
    queryFn: () => getLearningProfile(30, 0.6),
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const learningEffectivenessQuery = useQuery({
    queryKey: ['learning-effectiveness', 'admin'],
    queryFn: () => getLearningEffectiveness(30, 5),
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const circuitStateQuery = useQuery({
    queryKey: ['circuit-breaker-state', 'admin', circuitProfileScope],
    queryFn: () => getCircuitBreakerState(10, circuitProfileScope),
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const circuitEventsQuery = useQuery({
    queryKey: ['circuit-breaker-events', 'admin', circuitProfileScope],
    queryFn: () => getCircuitBreakerEvents(10, 0, circuitProfileScope),
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const queueMutation = useQueueScanMutation()
  const retryFailedMutation = useRetryFailedJobsMutation()
  const updateSettingsMutation = useUpdateRuntimeSettingsMutation()
  const pauseMutation = useMutation({
    mutationFn: () => pauseScans('admin'),
    onSuccess: async () => {
      toast.success('Scan pause requested')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to pause scans', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })
  const resumeMutation = useMutation({
    mutationFn: () => resumeScans('admin'),
    onSuccess: async () => {
      toast.success('Scan resume requested')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to resume scans', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })
  const stopMutation = useMutation({
    mutationFn: () => stopScans('admin'),
    onSuccess: async () => {
      toast.success('Stop requested for active scan')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to stop scan', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })
  
  const promoteV5Mutation = useMutation({
    mutationFn: promoteV5,
    onSuccess: async () => {
      toast.success('V5 candidate promoted')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['v5-overview'] }),
        queryClient.invalidateQueries({ queryKey: ['v5-models'] })
      ])
    },
    onError: (error) => toast.error('V5 promotion failed', { description: String(error) })
  })

  const rollbackV5Mutation = useMutation({
    mutationFn: rollbackV5,
    onSuccess: async () => {
      toast.success('V5 model rolled back')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['v5-overview'] }),
        queryClient.invalidateQueries({ queryKey: ['v5-models'] })
      ])
    },
    onError: (error) => toast.error('V5 rollback failed', { description: String(error) })
  })
  const triggerScanMutation = useMutation({
    mutationFn: triggerScanNow,
    onSuccess: async (payload) => {
      const trigger = (payload.trigger ?? {}) as Record<string, unknown>
      const paused = Boolean(trigger.paused)
      const restartedLoop = Boolean(trigger.restarted_loop)
      toast.success(paused ? 'Scan trigger queued, but runtime is paused' : 'Next autonomous scan triggered', {
        description: paused
          ? 'Resume scans to let the queued trigger run.'
          : restartedLoop
            ? 'The autonomous loop was restarted before queuing the trigger.'
            : 'The autonomous loop has been woken for the next scan cycle.',
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to trigger autonomous scan', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })
  const depositMutation = useMutation({
    mutationFn: depositPaperBalance,
    onSuccess: async () => {
      toast.success('Paper balance updated')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['paper-balance'] }),
        queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
        queryClient.invalidateQueries({ queryKey: ['portfolio', 'app-shell'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to deposit paper funds', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })
  const resetCircuitMutation = useMutation({
    mutationFn: () => resetCircuitBreaker(circuitProfileScope),
    onSuccess: async () => {
      toast.success('Circuit breaker reset')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['circuit-breaker-state', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['circuit-breaker-events', 'admin'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to reset circuit breaker', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })
  const updateCircuitSettingsMutation = useMutation({
    mutationFn: (payload: Record<string, string | number>) => updateCircuitBreakerSettings(payload, circuitProfileScope),
    onSuccess: async () => {
      toast.success('Circuit breaker settings updated')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['runtime-settings', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['runtime-settings', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['circuit-breaker-state', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['circuit-breaker-events', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['circuit-breaker-state', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['operator-alerts', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['operator-alerts', 'app-shell'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to update circuit breaker settings', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })
  const resetPaperMutation = useMutation({
    mutationFn: resetPaperBalance,
    onSuccess: async () => {
      toast.success('Paper balance reset')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['paper-balance'] }),
        queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
        queryClient.invalidateQueries({ queryKey: ['portfolio', 'app-shell'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to reset paper balance', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })
  const reconcilePaperMutation = useMutation({
    mutationFn: reconcilePaperBalance,
    onSuccess: async (payload) => {
      const summary = (payload.reconciliation ?? {}) as Record<string, unknown>
      toast.success('Paper balance reconciled', {
        description: `${formatNumber(summary.reconciled_orders, 0)} legacy open orders reserved against budget.`,
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['paper-balance'] }),
        queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
        queryClient.invalidateQueries({ queryKey: ['portfolio', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['orders'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to reconcile paper balance', { description: error instanceof Error ? error.message : 'Unknown error' })
    },
  })

  const health = healthQuery.data ?? null
  const queue = (jobsQuery.data ?? {}) as JobQueueSnapshot
  const settings = settingsQuery.data ?? {}
  const traceItems = logsQuery.data?.items?.slice(0, 14) ?? []
  const operatorAlerts = alertsQuery.data?.items?.slice(0, 8) ?? []
  const failureRows = ((failuresQuery.data?.items ?? []) as FailureRecord[]) ?? []
  const failureSummary = (failureSummaryQuery.data ?? { summary: {} }) as FailureSummaryPayload
  const weaknessProfile = (weaknessQuery.data ?? { profile: {} }) as WeaknessProfilePayload
  const learningPayload = (learningQuery.data ?? { profile: {} }) as LearningProfilePayload
  const learningProfile = learningPayload.profile ?? {}
  const learningEffectiveness = (learningEffectivenessQuery.data?.report ?? learningPayload.effectiveness_summary ?? { adjustments: [] }) as LearningEffectivenessPayload['report'] & Record<string, unknown>
  const learningEngineEnabled = normalizeBooleanSetting(settings.LEARNING_ENGINE_ENABLED) === 'true'
  const learningStatusLabel = learningEngineEnabled
    ? (learningPayload.active ? 'Learning Active' : 'Learning Inactive')
    : 'Learning Disabled'
  const circuitState = (circuitStateQuery.data?.state ?? { status: 'CLOSED' }) as CircuitBreakerState
  const circuitEvents = ((circuitEventsQuery.data?.items ?? []) as CircuitBreakerEvent[]) ?? []
  const calibration = calibrationQuery.data ?? { summary: {}, scopes: [] }
  const v5Overview = v5OverviewQuery.data ?? null
  const v5Comparison = v5ComparisonQuery.data ?? null
  const v5Readiness = v5ReadinessQuery.data ?? null
  const v5GateReport = v5GateReportQuery.data ?? null
  const paperBalance = (paperBalanceQuery.data ?? { account: {}, balance: 0, default_balance: 0 }) as PaperAccountPayload
  const reconciliation = (paperBalance.reconciliation ?? {}) as Record<string, unknown>
  const queueItems = (queue.items ?? []) as JobItem[]
  const scanControl = ((queue.control ?? health?.scan_control ?? {}) as ScanControlState)
  const scanControlStatus = String(scanControl.active_status ?? 'IDLE').toUpperCase()
  const desiredScanState = String(scanControl.desired_state ?? 'RUNNING').toUpperCase()
  const isScanPaused = desiredScanState === 'PAUSED'
  const fallbackActiveJob = queueItems.find((item) => ['RUNNING', 'PAUSED', 'STOPPING'].includes(String(item.status ?? '').toUpperCase())) ?? null
  const activeScanRunId = String(scanControl.active_run_id ?? fallbackActiveJob?.run_id ?? '').trim() || null
  const hasActiveScan = Boolean(activeScanRunId)
  const effectiveScanControlStatus = hasActiveScan && scanControlStatus === 'IDLE'
    ? String(fallbackActiveJob?.status ?? 'RUNNING').toUpperCase()
    : scanControlStatus

  const engineStatus = String(health?.status ?? 'unknown')
  const completedScan = latestCompletedScan(queueItems)
  const latestCapBlock = latestDailyCapBlock(completedScan)
  const lastScanAt = formatTime(completedScan?.finished_at ?? completedScan?.created_at)
  const lastError = firstCriticalMessage(operatorAlerts, traceItems)

  const availableSymbols = preferLargerSymbolUniverse(symbolsQuery.data?.symbols, splitCsv(settings.AUTONOMOUS_SYMBOLS))
  const configuredIntervals = splitCsv(settings.AUTONOMOUS_INTERVALS)
  const availableIntervals = [...INTERVAL_OPTION_CATALOG]
  const availableModes = STRATEGY_MODE_CATALOG.map((item) => item.value)

  const queueStats = [
    {
      label: 'Pending',
      value: formatNumber(queue.pending, 0),
      note: 'Waiting for a worker slot.',
      accent: 'text-stone-950',
      icon: Workflow,
    },
    {
      label: 'Running',
      value: formatNumber(queue.running, 0),
      note: 'Currently in execution.',
      accent: toNumber(queue.running) > 0 ? 'text-teal-900' : 'text-stone-950',
      icon: ScanSearch,
    },
    {
      label: 'Completed',
      value: formatNumber(queue.completed, 0),
      note: 'Finished successfully.',
      accent: 'text-teal-900',
      icon: CheckCircle2,
    },
    {
      label: 'Failed',
      value: formatNumber(queue.failed, 0),
      note: 'Needs operator review.',
      accent: toNumber(queue.failed) > 0 ? 'text-rose-800' : 'text-stone-950',
      icon: XCircle,
    },
  ]

  const groupedSettings = groupSettings(settings)
  const [settingsDraft, setSettingsDraft] = useState<Record<string, string>>({})
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    Risk: true,
    Execution: false,
    Filters: false,
    Engine: false,
  })
  const [paperDepositDraft, setPaperDepositDraft] = useState('100')
  const sizingPreviewRows = [60, 75, 90].map((confidence) => ({
    confidence,
    ...computeSizingPreview(confidence, toNumber(paperBalance.balance), settingsDraft),
  }))
  const enabledModes = splitCsv(settingsDraft.AUTONOMOUS_MODES ?? settings.AUTONOMOUS_MODES)
  const selectedModeSet = new Set(enabledModes)
  const globalIntervalSet = new Set(splitCsv(settingsDraft.AUTONOMOUS_INTERVALS ?? settings.AUTONOMOUS_INTERVALS))
  const modeIntervalRows = STRATEGY_MODE_CATALOG.map((mode) => {
    const key = modeIntervalSettingKey(mode.value)
    const configured = splitCsv(settingsDraft[key] ?? settings[key] ?? '')
    const selected = configured.filter((interval) => availableIntervals.includes(interval as (typeof INTERVAL_OPTION_CATALOG)[number]))
    return {
      ...mode,
      key,
      selected,
      enabled: selectedModeSet.has(mode.value),
    }
  })
  const modeIntervalPolicy = Object.fromEntries(
    modeIntervalRows.map((mode) => [mode.value, mode.selected.length ? mode.selected : configuredIntervals]),
  )

  useEffect(() => {
    setSettingsDraft(settings)
  }, [settings])

  function setDraftValue(key: string, value: string) {
    setSettingsDraft((current) => ({ ...current, [key]: value }))
  }

  function applyLearningPreset(values: Record<string, string>) {
    setSettingsDraft((current) => ({ ...current, ...values }))
  }

  function toggleCsvItem(key: string, item: string) {
    setSettingsDraft((current) => {
      const values = splitCsv(current[key])
      const nextValues = values.includes(item)
        ? values.filter((value) => value !== item)
        : [...values, item]
      return { ...current, [key]: nextValues.join(',') }
    })
  }

  const settingsDirty = JSON.stringify(settingsDraft) !== JSON.stringify(settings)

  const editableGroups = [
    {
      title: 'Risk',
      items: [
        { key: 'AUTONOMOUS_MIN_CONFIDENCE', type: 'number', min: 0, max: 100, step: 1, label: 'Min Confidence' },
        { key: 'MAX_TRADES_PER_DAY', type: 'number', min: 1, max: 50, step: 1, label: 'Max Trades Per Day' },
        { key: 'PAPER_DEFAULT_BALANCE', type: 'number', min: 1, max: 1000000, step: 1, label: 'Default Paper Balance' },
        { key: 'PAPER_POSITION_SIZE_MIN_PCT', type: 'number', min: 0, max: 100, step: 0.5, label: 'Paper Size Min %' },
        { key: 'PAPER_POSITION_SIZE_MAX_PCT', type: 'number', min: 0, max: 100, step: 0.5, label: 'Paper Size Max %' },
        { key: 'PAPER_POSITION_CONFIDENCE_FLOOR', type: 'number', min: 0, max: 100, step: 1, label: 'Paper Confidence Floor' },
        { key: 'PAPER_POSITION_CONFIDENCE_CEIL', type: 'number', min: 0, max: 100, step: 1, label: 'Paper Confidence Ceil' },
      ],
    },
    {
      title: 'Execution',
      items: [
        { key: 'AUTONOMOUS_ENABLED', type: 'toggle', label: 'Autonomous Enabled' },
        { key: 'CIRCUIT_BREAKER_ENABLED', type: 'toggle', label: 'Circuit Breaker Enabled' },
        { key: 'CIRCUIT_BREAKER_MANUAL_MODE', type: 'chips', options: ['AUTO', 'FORCE_OPEN', 'FORCE_CLOSED'], label: 'Circuit Breaker Manual Mode' },
        { key: 'AUTONOMOUS_SCAN_WORKERS', type: 'chips', options: ['1', '2', '4', '8', '16', '32', '64', '128'], label: 'Scan Workers' },
        { key: 'AUTONOMOUS_SCAN_INTERVAL_SECONDS', type: 'number', min: 30, max: 3600, step: 15, label: 'Scan Interval Seconds' },
        { key: 'AUTONOMOUS_MONITOR_INTERVAL_SECONDS', type: 'number', min: 5, max: 300, step: 5, label: 'Monitor Interval Seconds' },
        { key: 'CIRCUIT_BREAKER_LOOKBACK_TRADES', type: 'number', min: 1, max: 500, step: 1, label: 'Circuit Breaker Lookback Trades' },
        { key: 'CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES', type: 'number', min: 1, max: 50, step: 1, label: 'Circuit Breaker Max Consecutive Losses' },
        { key: 'CIRCUIT_BREAKER_MAX_FAILURE_RATE_PCT', type: 'number', min: 1, max: 100, step: 1, label: 'Circuit Breaker Max Failure Rate %' },
        { key: 'CIRCUIT_BREAKER_MAX_SEVERITY_AVG', type: 'number', min: 0, max: 10, step: 0.1, label: 'Circuit Breaker Max Severity Avg' },
        { key: 'CIRCUIT_BREAKER_COOLDOWN_MINUTES', type: 'number', min: 1, max: 1440, step: 1, label: 'Circuit Breaker Cooldown Minutes' },
        { key: 'CIRCUIT_BREAKER_DEGRADED_MULTIPLIER', type: 'number', min: 0, max: 1, step: 0.05, label: 'Circuit Breaker Degraded Multiplier' },
        { key: 'SYMBOL_THROTTLE_ENABLED', type: 'toggle', label: 'Symbol Throttle Enabled' },
        { key: 'SYMBOL_THROTTLE_LOOKBACK_TRADES', type: 'number', min: 3, max: 50, step: 1, label: 'Symbol Throttle Lookback Trades' },
        { key: 'SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS', type: 'number', min: 2, max: 10, step: 1, label: 'Max Consecutive Stop Hits' },
        { key: 'SYMBOL_THROTTLE_MAX_STOP_HIT_RATE_PCT', type: 'number', min: 1, max: 100, step: 1, label: 'Max Stop Hit Rate %' },
        { key: 'SYMBOL_THROTTLE_COOLDOWN_MINUTES', type: 'number', min: 1, max: 1440, step: 1, label: 'Symbol Throttle Cooldown Minutes' },
        { key: 'SYMBOL_THROTTLE_SEEDED_SYMBOLS', type: 'multi', options: availableSymbols, label: 'Seeded Throttle Symbols' },
      ],
    },
    {
      title: 'Filters',
      items: [
        { key: 'AUTONOMOUS_INTERVALS', type: 'multi', options: availableIntervals, label: 'Intervals' },
        { key: 'AUTONOMOUS_MODES', type: 'multi', options: availableModes, label: 'Modes' },
        { key: 'AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS', type: 'chips', options: ['BOTH', 'LONG_ONLY', 'SHORT_ONLY'], label: 'Allowed Trade Directions' },
        { key: 'AUTONOMOUS_SYMBOLS', type: 'multi', options: availableSymbols, label: 'Symbols' },
      ],
    },
    {
      title: 'Engine',
      items: [
        { key: 'LEARNING_ENGINE_ENABLED', type: 'toggle', label: 'Learning Engine Enabled' },
        { key: 'LEARNING_CALIBRATION_ENABLED', type: 'toggle', label: 'Learning Calibration Enabled' },
        { key: 'LEARNING_ADAPTIVE_STOP_ENABLED', type: 'toggle', label: 'Learning Adaptive Stop Enabled' },
        { key: 'V6_ACTIONABILITY_CONFIDENCE_ENABLED', type: 'toggle', label: 'V6 Final Actionability Confidence' },
        { key: 'LEARNING_LOOKBACK_DAYS', type: 'number', min: 1, max: 365, step: 1, label: 'Learning Lookback Days' },
        { key: 'LEARNING_MIN_CONFIDENCE', type: 'number', min: 0, max: 1, step: 0.05, label: 'Learning Min Confidence' },
        { key: 'LEARNING_REFRESH_SECONDS', type: 'number', min: 60, max: 86400, step: 30, label: 'Learning Refresh Seconds' },
        { key: 'ANALYZER_ENGINE_TIMEOUT_MS', type: 'number', min: 250, max: 10000, step: 50, label: 'Analyzer Timeout Ms' },
      ],
    },
  ] as const

  const criticalTraceCount = useMemo(
    () => traceItems.filter((item) => String(item.severity ?? '').toLowerCase().includes('error')).length,
    [traceItems],
  )

  const failedJobs = useMemo(
    () =>
      queueItems
        .filter((item) => {
          const status = String(item.status ?? '').toUpperCase()
          return status === 'FAILED' || status === 'DEAD_LETTER'
        })
        .slice(0, 5),
    [queueItems],
  )

  const runtimeOverview = [
    ['DB Status', String(health?.db_status ?? 'unknown')],
    ['Runtime', String(health?.runtime_status ?? 'unknown')],
    ['Exchange', String(health?.exchange_status ?? 'unknown')],
    ['Scan Control', `${effectiveScanControlStatus}${isScanPaused ? ' · paused' : ''}`],
    ['Paper Balance', `$${formatNumber(paperBalance.balance, 2)}`],
    ['Uptime', `${formatNumber(health?.uptime_seconds, 0)}s`],
    ['Active Alerts', formatNumber(health?.alert_summary?.total_active, 0)],
    ['Throttled symbols', formatNumber(health?.symbol_throttle?.total_throttled, 0)],
  ]
  const calibrationSummary = calibration.summary ?? {}
  const calibrationScopes = (calibration.scopes ?? []).slice(0, 6) as CalibrationScopeRow[]

  const defaultQuickScan = {
    symbols: availableSymbols.length ? availableSymbols.slice(0, 3) : ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
    intervals: configuredIntervals.length ? configuredIntervals.slice(0, 2) : ['15m', '1h'],
    modes: enabledModes.length ? enabledModes.slice(0, 2) : availableModes.slice(0, 2),
    scan_workers: 4,
  }

  function saveRuntimeSettings() {
    updateSettingsMutation.mutate(settingsDraft as RuntimeSettingsPayload)
  }

  const alertSeverityRows = summarizeAlertsBySeverity(operatorAlerts)
  const alertScopeRows = summarizeAlertsByScope(operatorAlerts)
  const failureSourceRows = topEntries(failureSummary.summary?.counts_by_failure_source, 5)
  const failureComponentRows = topEntries(failureSummary.summary?.counts_by_blamed_component, 5)
  const severityDistribution = useMemo(() => {
    const counts = new Map<number, number>()
    for (const row of failureRows) {
      const score = Math.max(1, Math.min(5, toNumber(row.severity_score, 0)))
      counts.set(score, (counts.get(score) ?? 0) + 1)
    }
    return [1, 2, 3, 4, 5].map((score) => [score, counts.get(score) ?? 0] as const)
  }, [failureRows])
  const topImprovements = useMemo(() => {
    const suggestions = (weaknessProfile.profile?.ranked_sources ?? [])
      .map((row) => ({
        source: String(row.failure_source ?? '--'),
        suggestion: String(row.best_improvement ?? '').trim(),
      }))
      .filter((row) => row.suggestion)
    return suggestions.slice(0, 3)
  }, [weaknessProfile.profile?.ranked_sources])
  const calibrationBuckets = learningPayload.calibration_data ?? learningProfile.confidence_calibration?.buckets ?? []
  const topLearningPenalties = learningPayload.top_penalties ?? learningProfile.top_penalties ?? []
  const learningLookbackDays = Number(learningPayload.profile?.lookback_days ?? learningEffectiveness?.lookback_days ?? 30)
  const learningMinConfidence = Number(learningProfile.min_confidence ?? 0.6)
  const learningMinSamples = Number(learningEffectiveness?.min_samples ?? 5)
  const queueOverviewStats = [
    ['Symbol universe', formatNumber(availableSymbols.length, 0), 'Markets available to the queue builder.'],
    ['Intervals live', formatNumber(configuredIntervals.length, 0), 'Configured timeframes the engine can scan.'],
    ['Modes enabled', formatNumber(enabledModes.length, 0), 'Execution families currently active in runtime settings.'],
    ['Default workers', String(settingsDraft.AUTONOMOUS_SCAN_WORKERS ?? settings.AUTONOMOUS_SCAN_WORKERS ?? '4'), 'Parallel fetch lanes for queued scans.'],
  ] as const
  const settingsOverviewCards = [
    ['Autonomous', normalizeBooleanSetting(settingsDraft.AUTONOMOUS_ENABLED ?? settings.AUTONOMOUS_ENABLED) === 'true' ? 'Enabled' : 'Disabled'],
    ['Daily cap', formatNumber(settingsDraft.MAX_TRADES_PER_DAY ?? settings.MAX_TRADES_PER_DAY, 0)],
    ['Min confidence', `${formatNumber(settingsDraft.AUTONOMOUS_MIN_CONFIDENCE ?? settings.AUTONOMOUS_MIN_CONFIDENCE, 0)}%`],
    ['Trade sides', String(settingsDraft.AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS ?? settings.AUTONOMOUS_ALLOWED_TRADE_DIRECTIONS ?? 'BOTH').replaceAll('_', ' ')],
    ['Scan cadence', `${formatNumber(settingsDraft.AUTONOMOUS_SCAN_INTERVAL_SECONDS ?? settings.AUTONOMOUS_SCAN_INTERVAL_SECONDS, 0)}s`],
  ] as const
  const modePolicySummaryCards = modeIntervalRows.map((mode) => [
    mode.label,
    mode.selected.length ? mode.selected.join(' · ') : 'Uses global set',
  ] as const)
  const activeLearningPresetId = useMemo(() => {
    const engineEnabled = normalizeBooleanSetting(settingsDraft.LEARNING_ENGINE_ENABLED ?? settings.LEARNING_ENGINE_ENABLED)
    const calibrationEnabled = normalizeBooleanSetting(settingsDraft.LEARNING_CALIBRATION_ENABLED ?? settings.LEARNING_CALIBRATION_ENABLED)
    const adaptiveStopEnabled = normalizeBooleanSetting(settingsDraft.LEARNING_ADAPTIVE_STOP_ENABLED ?? settings.LEARNING_ADAPTIVE_STOP_ENABLED)
    const matched = LEARNING_PRESETS.find((preset) =>
      preset.values.LEARNING_ENGINE_ENABLED === engineEnabled &&
      preset.values.LEARNING_CALIBRATION_ENABLED === calibrationEnabled &&
      preset.values.LEARNING_ADAPTIVE_STOP_ENABLED === adaptiveStopEnabled,
    )
    return matched?.id ?? null
  }, [settings.LEARNING_ADAPTIVE_STOP_ENABLED, settings.LEARNING_CALIBRATION_ENABLED, settings.LEARNING_ENGINE_ENABLED, settingsDraft.LEARNING_ADAPTIVE_STOP_ENABLED, settingsDraft.LEARNING_CALIBRATION_ENABLED, settingsDraft.LEARNING_ENGINE_ENABLED])
  const throttledSymbols = health?.symbol_throttle?.throttled_symbols ?? []
  const adminTabs: Array<{ id: AdminTab; label: string; badge?: string | null; badgeTone?: 'bad' | 'warn' | 'neutral' }> = [
    { id: 'overview', label: 'Overview' },
    { id: 'queue', label: 'Scan queue', badge: toNumber(queue.failed) > 0 ? formatNumber(queue.failed, 0) : null, badgeTone: 'bad' },
    { id: 'intelligence', label: 'Failures & learning' },
    { id: 'budget', label: 'Paper budget' },
    { id: 'settings', label: 'Settings', badge: settingsDirty ? '●' : null, badgeTone: 'warn' },
    {
      id: 'alerts',
      label: 'Alerts',
      badge: operatorAlerts.length ? String(operatorAlerts.length) : null,
      badgeTone: operatorAlerts.some((item) => String(item.severity ?? '').toLowerCase() === 'critical') ? 'bad' : 'warn',
    },
  ]
  const visibleAdminTabs = useMemo(
    () => adminTabs.filter((tab) => (visibleTabs?.length ? visibleTabs.includes(tab.id) : true)),
    [adminTabs, visibleTabs],
  )
  const filteredQueueJobs = useMemo(() => {
    const term = jobFilter.trim().toLowerCase()
    if (!term) return queueItems
    return queueItems.filter((item) => {
      const haystack = [
        String(item.run_id ?? ''),
        String(item.status ?? ''),
        String(item.worker_id ?? ''),
        String(item.error_text ?? ''),
        String(item.created_at ?? ''),
      ].join(' ').toLowerCase()
      return haystack.includes(term)
    })
  }, [jobFilter, queueItems])
  const refreshRuntime = () => {
    void jobsQuery.refetch()
    void healthQuery.refetch()
    void logsQuery.refetch()
    void alertsQuery.refetch()
    void settingsQuery.refetch()
    void paperBalanceQuery.refetch()
    void calibrationQuery.refetch()
    void symbolsQuery.refetch()
    void failuresQuery.refetch()
    void failureSummaryQuery.refetch()
    void weaknessQuery.refetch()
    void learningQuery.refetch()
    void learningEffectivenessQuery.refetch()
  }
  const toggleGroup = (name: string) => {
    setOpenGroups((current) => ({ ...current, [name]: !current[name] }))
  }

  useEffect(() => {
    if (lockedTab) {
      setActiveTab(lockedTab)
      return
    }
    setActiveTab(initialTab)
  }, [initialTab, lockedTab])

  function handleCircuitProfileScopeChange(nextScope: string) {
    const nextParams = new URLSearchParams(searchParams)
    if (nextScope === DEFAULT_PROFILE_SCOPE) {
      nextParams.delete('profile')
    } else {
      nextParams.set('profile', nextScope)
    }
    setSearchParams(nextParams)
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <section className="overflow-hidden rounded-[1.5rem] border border-stone-900/8 bg-white/90 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="flex flex-col gap-3 border-b border-stone-900/8 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <div className="flex items-center gap-2">
                <Circle
                  className={`h-2.5 w-2.5 ${engineStatus.toLowerCase() === 'healthy' ? 'fill-teal-700 text-teal-700' : engineStatus.toLowerCase() === 'degraded' ? 'fill-amber-600 text-amber-600' : 'fill-rose-700 text-rose-700'}`}
                  strokeWidth={0}
                />
                <span className="font-semibold text-stone-950">{engineStatus}</span>
              </div>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">Runtime <strong className="text-stone-950">{String(health?.runtime_status ?? 'unknown')}</strong></span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">Balance <strong className="text-stone-950">${formatNumber(paperBalance.balance, 2)}</strong></span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">Last scan <strong className="text-stone-950">{lastScanAt}</strong></span>
              <span className="text-stone-400">·</span>
              <span className="text-stone-600">Uptime <strong className="text-stone-950">{formatNumber(health?.uptime_seconds, 0)}s</strong></span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge label={`Scan: ${effectiveScanControlStatus}`} tone={isScanPaused ? 'warn' : hasActiveScan ? 'good' : 'neutral'} />
              {toNumber(queue.failed) > 0 ? <StatusBadge label={`${formatNumber(queue.failed, 0)} failed`} tone="bad" /> : null}
              {operatorAlerts.length ? (
                <button
                  type="button"
                  onClick={() => setActiveTab('alerts')}
                  className="rounded-full border border-stone-900/8 bg-stone-950/[0.03] px-3 py-1.5 text-xs font-semibold text-stone-700"
                >
                  Alerts {operatorAlerts.length}
                </button>
              ) : null}
            </div>
          </div>

          {!hideTabBar ? (
          <div className="flex overflow-x-auto border-b border-stone-900/8 bg-white px-2">
            {visibleAdminTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`inline-flex items-center gap-2 rounded-t-2xl border-b-2 px-4 py-3 text-sm font-medium transition-[color,background-color,transform,border-color] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
                  activeTab === tab.id
                    ? 'border-stone-950 bg-stone-950/[0.03] text-stone-950'
                    : 'border-transparent text-stone-500 hover:bg-stone-950/[0.02] hover:text-stone-950'
                }`}
              >
                {tab.label}
                {tab.badge ? (
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                    tab.badgeTone === 'bad' ? 'bg-rose-100 text-rose-800' :
                      tab.badgeTone === 'warn' ? 'bg-amber-100 text-amber-800' :
                        'bg-stone-100 text-stone-600'
                  }`}>
                    {tab.badge}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
          ) : null}

          <div key={activeTab} className="tab-panel-enter grid gap-4 p-4">
            {activeTab === 'overview' ? (
              <>
                <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {queueStats.map((item) => (
                    <div
                      key={item.label}
                      className="rounded-[1.4rem] border border-stone-900/8 bg-white/86 p-4 shadow-[0_16px_30px_rgba(77,62,40,0.05)]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{item.label}</p>
                        <item.icon className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
                      </div>
                      <p className={`mt-3 text-3xl font-semibold tracking-[-0.06em] ${item.accent}`}>{item.value}</p>
                      <p className="mt-2 text-sm leading-6 text-stone-500">{item.note}</p>
                    </div>
                  ))}
                </section>

                <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/86 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="grid gap-1">
                      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Scan Controls</p>
                      <p className="text-sm font-semibold text-stone-950">
                        {hasActiveScan ? `${effectiveScanControlStatus} · ${String(activeScanRunId ?? '--')}` : 'No active scan'}
                      </p>
                      {scanControl.current_task ? (
                        <p className="text-sm text-stone-500">
                          {String(scanControl.current_task.symbol ?? '--')} · {String(scanControl.current_task.interval ?? '--')} · {String(scanControl.current_task.mode ?? '--')}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => queueMutation.mutate(defaultQuickScan)}
                        disabled={queueMutation.isPending}
                        className="inline-flex items-center gap-2 rounded-full bg-stone-950 px-4 py-2.5 text-sm font-semibold text-stone-50 transition hover:bg-stone-900 disabled:opacity-60"
                      >
                        <Radar className="h-4 w-4" strokeWidth={1.8} />
                        {queueMutation.isPending ? 'Submitting…' : 'Quick Scan'}
                      </button>
                      <button
                        type="button"
                        onClick={() => pauseMutation.mutate()}
                        disabled={pauseMutation.isPending || isScanPaused}
                        className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                      >
                        <Pause className="h-4 w-4" strokeWidth={1.8} />
                        Pause
                      </button>
                      <button
                        type="button"
                        onClick={() => resumeMutation.mutate()}
                        disabled={resumeMutation.isPending || (!isScanPaused && !scanControl.stop_requested)}
                        className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                      >
                        <Play className="h-4 w-4" strokeWidth={1.8} />
                        Resume
                      </button>
                      <button
                        type="button"
                        onClick={() => stopMutation.mutate()}
                        disabled={stopMutation.isPending || !hasActiveScan}
                        className="inline-flex items-center gap-2 rounded-full border border-rose-900/10 bg-rose-50/90 px-4 py-2.5 text-sm font-semibold text-rose-900 transition hover:bg-rose-50 disabled:opacity-60"
                      >
                        <Square className="h-4 w-4" strokeWidth={1.8} />
                        Stop
                      </button>
                      <button
                        type="button"
// @ts-expect-error pre-existing
                        onClick={() => triggerScanMutation.mutate()}
                        disabled={triggerScanMutation.isPending}
                        className="inline-flex items-center gap-2 rounded-full border border-teal-900/12 bg-teal-50/80 px-4 py-2.5 text-sm font-semibold text-teal-900 transition hover:bg-teal-50 disabled:opacity-60"
                      >
                        <TimerReset className="h-4 w-4" strokeWidth={1.8} />
                        {triggerScanMutation.isPending ? 'Triggering…' : 'Scan Now'}
                      </button>
                      <button
                        type="button"
                        onClick={refreshRuntime}
                        className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
                      >
                        <RefreshCw className="h-4 w-4" strokeWidth={1.8} />
                        Refresh
                      </button>
                    </div>
                  </div>
                </section>

                <section className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Engine Runtime</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Current backend conditions</h2>
            </div>
            <div className="grid gap-4 lg:grid-cols-[0.78fr_1.22fr]">
              <div className="grid gap-3">
                {runtimeOverview.map(([label, value]) => (
                  <div key={label} className="rounded-[1.3rem] bg-stone-950/[0.03] p-4">
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                    <p className="mt-2 text-sm font-semibold leading-6 text-stone-950">{value}</p>
                  </div>
                ))}
              </div>

              <div className="grid gap-3">
                <div className={`rounded-[1.35rem] border p-4 ${lastError ? 'border-rose-900/10 bg-rose-50/90' : 'border-stone-900/8 bg-white'}`}>
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Last Error</p>
                  <p className={`mt-3 text-sm leading-7 ${lastError ? 'font-semibold text-rose-900' : 'text-stone-500'}`}>
                    {lastError || 'none'}
                  </p>
                </div>

                {failedJobs.length ? (
                  <div className="rounded-[1.35rem] border border-rose-900/10 bg-rose-50/90 p-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-rose-900">
                      <AlertTriangle className="h-4 w-4" strokeWidth={1.8} />
                      Failed Jobs Detail
                    </div>
                    <div className="mt-3 grid gap-2">
                      {failedJobs.map((item, index) => (
                        <div key={`${String(item.id ?? index)}-${String(item.created_at ?? '')}`} className="rounded-[1rem] bg-white/80 px-3 py-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="text-sm font-semibold text-stone-950">Job #{String(item.id ?? '--')}</span>
                            <span className="text-xs font-mono text-stone-500">{formatTime(item.created_at)}</span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-rose-900">{String(item.error_text ?? 'No error text recorded.')}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-[1.35rem] border border-stone-900/8 bg-white p-4 text-sm text-stone-500">
                    No failed scan jobs in the current window.
                  </div>
                )}
              </div>
            </div>
          </div>

          <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
            <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="grid gap-1">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Trace Feed</p>
                <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Compact engine activity log</h2>
              </div>
              <div className="flex items-center gap-3">
                <span className="rounded-full border border-stone-900/8 bg-stone-950/[0.03] px-3 py-2 text-sm text-stone-600">
                  {traceItems.length} events
                </span>
                <Link to="/logs" className="inline-flex items-center gap-2 text-sm font-semibold text-teal-900">
                  Open Logs
                  <ArrowRight className="h-4 w-4" strokeWidth={1.8} />
                </Link>
              </div>
            </div>

            <div className="mb-3 flex flex-wrap items-center justify-between gap-3 text-sm text-stone-500">
              <span>
                {criticalTraceCount > 0 ? (
                  <>
                    <span className="font-semibold text-rose-800">{criticalTraceCount}</span> critical events in the latest window
                  </>
                ) : (
                  <>
                    <span className="font-semibold text-teal-900">No critical events</span> in the latest window
                  </>
                )}
              </span>
              <span>Newest first</span>
            </div>

            <div className="max-h-[280px] overflow-y-auto rounded-[1.25rem] border border-stone-900/8 bg-stone-950/[0.02]">
              {traceItems.length ? (
                traceItems.map((item, index) => (
                  <div
                    key={`${String(item.timestamp_utc)}-${index}`}
                    className={`grid grid-cols-[7.5rem_5rem_6rem_minmax(0,1fr)] gap-3 border-b border-stone-900/6 px-3 py-3 text-sm last:border-b-0 ${severityClasses(String(item.severity ?? 'INFO'))}`}
                  >
                    <div className="font-mono text-xs uppercase tracking-[0.16em] opacity-70">{formatTime(item.timestamp_utc)}</div>
                    <div className="font-semibold">{String(item.severity ?? 'INFO')}</div>
                    <div className="truncate font-semibold">{String(item.symbol ?? item.category ?? 'ENGINE')}</div>
                    <div className="truncate">{compactLogMessage(item)}</div>
                  </div>
                ))
              ) : (
                <div className="p-4">
                  <EmptyState message="Trace events will appear here once the engine records them." />
                </div>
              )}
            </div>
          </section>
        </section>

                <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                  <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div className="grid gap-1">
                      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Universe Throttle</p>
                      <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Symbol suppression state</h2>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-sm text-stone-500">
                      <span className="rounded-full border border-stone-900/8 bg-stone-950/[0.03] px-3 py-1.5">
                        {health?.symbol_throttle?.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                      <span className="rounded-full border border-stone-900/8 bg-stone-950/[0.03] px-3 py-1.5">
                        {formatNumber(health?.symbol_throttle?.total_throttled, 0)} throttled
                      </span>
                    </div>
                  </div>
                  {throttledSymbols.length ? (
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {throttledSymbols.slice(0, 6).map((item) => (
                        <div key={String(item.symbol ?? '--')} className="rounded-[1.2rem] border border-amber-900/10 bg-amber-50/70 p-4">
                          <div className="flex items-center justify-between gap-3">
                            <p className="text-sm font-semibold text-stone-950">{String(item.symbol ?? '--')}</p>
                            <span className="rounded-full bg-white/80 px-2 py-1 text-[0.72rem] font-semibold text-amber-900">
                              {formatNumber(item.stop_hit_rate_pct, 1)}% stops
                            </span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-stone-700">{String(item.reason ?? 'Symbol throttled by safety policy.')}</p>
                          <div className="mt-3 flex flex-wrap gap-2 text-xs text-stone-600">
                            <span className="rounded-full bg-white/80 px-2 py-1">Rules {String((item.active_rules ?? []).join(', ') || '--')}</span>
                            <span className="rounded-full bg-white/80 px-2 py-1">Cooldown {item.cooldown_remaining_minutes != null ? `${formatNumber(item.cooldown_remaining_minutes, 0)}m` : '--'}</span>
                            <span className="rounded-full bg-white/80 px-2 py-1">Spread {formatNumber((item.microstructure as Record<string, unknown> | undefined)?.avg_spread_bps, 2)}bps</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-[1.25rem] border border-stone-900/8 bg-stone-950/[0.02] p-4 text-sm text-stone-500">
                      No symbols are currently throttled.
                    </div>
                  )}
                </section>

                <section className="grid gap-4 xl:grid-cols-2">
                  <div className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <div className="grid gap-1">
                        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Calibration readiness</p>
                        <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Training coverage</h2>
                      </div>
                      <button
                        type="button"
                        onClick={() => setActiveTab('intelligence')}
                        className="text-sm font-semibold text-teal-900 hover:underline"
                      >
                        Full detail →
                      </button>
                    </div>
                    <div className="grid gap-3">
                      {calibrationScopes.length ? calibrationScopes.map((scope) => {
                        const totalNeeded = toNumber(scope.labeled, 0) + toNumber(scope.remaining_to_threshold, 0)
                        const progress = scope.ready_for_calibration ? 100 : totalNeeded > 0 ? (toNumber(scope.labeled, 0) / totalNeeded) * 100 : 0
                        return (
                          <div key={`${scope.regime ?? 'UNKNOWN'}-${scope.mode ?? 'UNKNOWN'}`} className="grid gap-2">
                            <div className="flex items-center justify-between gap-3 text-sm">
                              <span className="font-semibold text-stone-950">{scope.regime} · {scope.mode}</span>
                              <span className={scope.ready_for_calibration ? 'text-xs font-semibold text-teal-900' : 'text-xs text-stone-500'}>
                                {scope.ready_for_calibration ? 'Ready' : `${formatNumber(scope.labeled, 0)} / ${formatNumber(totalNeeded, 0)}`}
                              </span>
                            </div>
                            <div className="h-1.5 overflow-hidden rounded-full bg-stone-950/10">
                              <div
                                className={`h-full rounded-full ${scope.ready_for_calibration ? 'bg-teal-700' : 'bg-amber-600'}`}
                                style={{ width: `${Math.min(progress, 100)}%` }}
                              />
                            </div>
                          </div>
                        )
                      }) : <EmptyState message="Calibration scopes will appear here once outcomes accumulate." />}
                    </div>
                  </div>

                  <div className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                    <div className="mb-4 flex items-center justify-between gap-3">
                      <div className="grid gap-1">
                        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Learning health</p>
                        <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Adjustment readiness</h2>
                      </div>
                      <button
                        type="button"
                        onClick={() => setActiveTab('intelligence')}
                        className="text-sm font-semibold text-teal-900 hover:underline"
                      >
                        Full detail →
                      </button>
                    </div>
                    <div className="grid gap-3">
                      {[
                        ['Learning', learningPayload.active ? 'Active' : 'Inactive'],
                        ['Health score', formatNumber(learningEffectiveness?.health_score, 2)],
                        ['Top stop multiplier', `x${formatNumber(learningProfile.stop_loss_adjustments?.base_multiplier ?? 1, 2)}`],
                        ['Top penalty', String(topLearningPenalties[0]?.label ?? topLearningPenalties[0]?.component ?? '--')],
                      ].map(([label, value]) => (
                        <div key={String(label)} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3">
                          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                          <p className="mt-2 text-sm font-semibold text-stone-950">{value}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === 'queue' ? (
              <>
                <section className="rounded-[1.6rem] border border-stone-900/8 bg-white/86 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="grid gap-1">
                      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Scan Queue</p>
                      <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Queue work and control active execution</h2>
                      <p className="text-sm leading-6 text-stone-500">All scan actions live here. This is the only operator control surface for pause, resume, stop, and manual queueing.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge label={queueMutation.isPending ? 'Submitting' : effectiveScanControlStatus} tone={queueMutation.isPending ? 'warn' : hasActiveScan ? 'good' : 'neutral'} />
                      {hasActiveScan ? (
                        <span className="rounded-full border border-stone-900/8 bg-stone-950/[0.03] px-3 py-2 text-xs font-medium text-stone-700">
                          Active {String(activeScanRunId ?? '--')}
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <div className="mt-4 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
                    <div className="grid gap-4">
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                        {queueOverviewStats.map(([label, value, note]) => (
                          <div key={label} className="rounded-[1.2rem] border border-stone-900/8 bg-white/90 p-4">
                            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                            <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-950">{value}</p>
                            <p className="mt-2 text-sm leading-6 text-stone-500">{note}</p>
                          </div>
                        ))}
                      </div>

                      {latestCapBlock ? (
                        <div className="rounded-[1.2rem] border border-amber-900/10 bg-amber-50/80 px-4 py-4">
                          <div className="flex items-center gap-2 text-sm font-semibold text-amber-900">
                            <AlertTriangle className="h-4 w-4" strokeWidth={1.8} />
                            Latest completed scan hit the daily trade cap
                          </div>
                          <p className="mt-2 text-sm leading-6 text-amber-900/90">
                            {latestCapBlock.runId} created no orders because execution was capped for the day. Daily trades recorded: {formatNumber(latestCapBlock.dailyTrades, 0)}. Skipped due to cap: {formatNumber(latestCapBlock.dailyCapSkipped, 0)}.
                          </p>
                        </div>
                      ) : null}

                      <div className="grid gap-3 rounded-[1.2rem] border border-stone-900/8 bg-stone-950/[0.03] px-4 py-4 md:grid-cols-[1fr_auto] md:items-center">
                        <div className="grid gap-1">
                          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Active Scan State</p>
                          <p className="text-sm font-semibold text-stone-950">
                            {hasActiveScan ? `${effectiveScanControlStatus} · ${String(activeScanRunId ?? '--')}` : 'No active scan'}
                          </p>
                          {scanControl.current_task ? (
                            <p className="text-sm text-stone-500">
                              {String(scanControl.current_task.symbol ?? '--')} · {String(scanControl.current_task.interval ?? '--')} · {String(scanControl.current_task.mode ?? '--')}
                            </p>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => pauseMutation.mutate()}
                            disabled={pauseMutation.isPending || isScanPaused}
                            className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                          >
                            <Pause className="h-4 w-4" strokeWidth={1.8} />
                            Pause
                          </button>
                          <button
                            type="button"
                            onClick={() => resumeMutation.mutate()}
                            disabled={resumeMutation.isPending || (!isScanPaused && !scanControl.stop_requested)}
                            className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                          >
                            <Play className="h-4 w-4" strokeWidth={1.8} />
                            Resume
                          </button>
                          <button
                            type="button"
                            onClick={() => stopMutation.mutate()}
                            disabled={stopMutation.isPending || !hasActiveScan}
                            className="inline-flex items-center gap-2 rounded-full border border-rose-900/10 bg-rose-50/90 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-50 disabled:opacity-60"
                          >
                            <Square className="h-4 w-4" strokeWidth={1.8} />
                            Stop
                          </button>
                          <button
                            type="button"
// @ts-expect-error pre-existing
                            onClick={() => triggerScanMutation.mutate()}
                            disabled={triggerScanMutation.isPending}
                            className="inline-flex items-center gap-2 rounded-full border border-teal-900/12 bg-teal-50/80 px-4 py-2 text-sm font-semibold text-teal-900 transition hover:bg-teal-50 disabled:opacity-60"
                          >
                            <TimerReset className="h-4 w-4" strokeWidth={1.8} />
                            {triggerScanMutation.isPending ? 'Triggering…' : 'Scan Now'}
                          </button>
                          <button
                            type="button"
                            onClick={() => retryFailedMutation.mutate(25)}
                            disabled={retryFailedMutation.isPending || toNumber(queue.failed) <= 0}
                            className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                          >
                            <AlertTriangle className="h-4 w-4" strokeWidth={1.8} />
                            Retry Failed
                          </button>
                        </div>
                      </div>

                      <div className="grid gap-3 rounded-[1.25rem] border border-stone-900/8 bg-white/92 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Mode Availability</p>
                            <p className="mt-1 text-sm text-stone-500">All strategy families stay visible here, even when currently disabled in runtime settings.</p>
                          </div>
                          <span className="rounded-full bg-stone-950/[0.03] px-3 py-1.5 text-xs font-semibold text-stone-600">
                            {formatNumber(enabledModes.length, 0)} active
                          </span>
                        </div>
                        <div className="grid gap-3 lg:grid-cols-3">
                          {STRATEGY_MODE_CATALOG.map((mode) => {
                            const active = selectedModeSet.has(mode.value)
                            return (
                              <div
                                key={mode.value}
                                className={`rounded-[1.1rem] border px-4 py-4 transition-[transform,box-shadow,border-color,background-color] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
                                  active
                                    ? 'border-teal-900/12 bg-teal-50/70 shadow-[0_12px_24px_rgba(20,83,45,0.08)]'
                                    : 'border-stone-900/8 bg-stone-950/[0.03]'
                                }`}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <p className="text-sm font-semibold text-stone-950">{mode.label}</p>
                                  <StatusBadge label={active ? 'Enabled' : 'Disabled'} tone={active ? 'good' : 'neutral'} />
                                </div>
                                <p className="mt-2 text-sm leading-6 text-stone-500">{mode.description}</p>
                              </div>
                            )
                          })}
                        </div>
                      </div>

                      <ScanJobForm
                        onSubmit={(payload) => queueMutation.mutate(payload)}
                        isSubmitting={queueMutation.isPending}
                        availableSymbols={availableSymbols}
                        availableIntervals={configuredIntervals}
                        availableModes={availableModes}
                        defaultModes={enabledModes.length ? enabledModes : availableModes.slice(0, 2)}
                        modeIntervalPolicy={modeIntervalPolicy}
                      />
                    </div>

                    <div className="rounded-[1.35rem] border border-stone-900/8 bg-white/90 p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="grid gap-1">
                          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Job Table</p>
                          <p className="text-sm text-stone-500">Filter by run ID, status, worker, or error text.</p>
                        </div>
                        <input
                          value={jobFilter}
                          onChange={(event) => setJobFilter(event.target.value)}
                          placeholder="Filter by run ID or status…"
                          className="h-9 w-full max-w-64 rounded-2xl border border-stone-900/8 bg-white px-3 text-sm outline-none transition focus:border-teal-900/20 focus:ring-2 focus:ring-teal-900/10"
                        />
                      </div>
                      <div className="mt-4 max-h-[34rem] overflow-auto rounded-[1rem] border border-stone-900/8">
                        <table className="min-w-full divide-y divide-stone-900/8 text-sm">
                          <thead className="bg-stone-950/[0.03] text-stone-600">
                            <tr>
                              <th className="px-4 py-3 text-left font-medium">Run ID</th>
                              <th className="px-4 py-3 text-left font-medium">Status</th>
                              <th className="px-4 py-3 text-left font-medium">Worker</th>
                              <th className="px-4 py-3 text-left font-medium">Created</th>
                              <th className="px-4 py-3 text-left font-medium">Error</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-stone-900/8">
                            {filteredQueueJobs.length ? filteredQueueJobs.map((item, index) => (
                              <tr key={`${String(item.id ?? index)}-${String(item.created_at ?? '')}`}>
                                <td className="px-4 py-3 font-mono text-xs text-stone-700">{String(item.run_id ?? '--')}</td>
                                <td className="px-4 py-3"><StatusBadge label={String(item.status ?? '--')} tone={statusTone(String(item.status ?? '')) === 'tone-bad' ? 'bad' : statusTone(String(item.status ?? '')) === 'tone-warn' ? 'warn' : statusTone(String(item.status ?? '')) === 'tone-good' ? 'good' : 'neutral'} /></td>
                                <td className="px-4 py-3 text-stone-700">{String(item.worker_id ?? '--')}</td>
                                <td className="px-4 py-3 text-stone-700">{formatTime(item.created_at)}</td>
                                <td className="max-w-[22rem] truncate px-4 py-3 text-stone-500">{String(item.error_text ?? '—')}</td>
                              </tr>
                            )) : (
                              <tr>
                                <td colSpan={5} className="px-4 py-8">
                                  <EmptyState message="No queue rows matched the current filter." />
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </section>
              </>
            ) : null}

            {activeTab === 'intelligence' ? (
              <>
                <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)] mb-6">
                  <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="grid gap-1">
                      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">V5 Engine Registry</p>
                      <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">V5 Readiness and Live Shadow Comparison</h2>
                      <p className="text-sm leading-6 text-stone-500">View readiness state, shadow reports and trigger candidate promotions.</p>
                    </div>
                    <div className="flex items-center gap-2">
                       <StatusBadge label={v5Readiness?.readiness_state ?? 'LOADING'} tone={v5Readiness?.readiness_state === 'PROMOTION_READY' ? 'good' : 'neutral'} />
                       {v5Readiness?.readiness_state === 'PROMOTION_READY' && (
                         <button onClick={() => promoteV5Mutation.mutate()} className="inline-flex items-center gap-2 rounded-full border border-teal-900/10 bg-teal-50 px-4 py-2 text-sm font-semibold text-teal-900 transition hover:bg-teal-100">
                           Promote Candidate
                         </button>
                       )}
                       {v5Overview?.active_model_version && (
                         <button onClick={() => rollbackV5Mutation.mutate()} className="inline-flex items-center gap-2 rounded-full border border-rose-900/10 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100">
                           Rollback Active
                         </button>
                       )}
                    </div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 mb-4">
                    {[
                      ['Active Win Model', v5Overview?.active_model_version ?? '--', ''],
                      ['Active Action', v5Overview?.active_action_version ?? '--', ''],
                      ['Readiness', v5Readiness?.readiness_state ?? '--', ''],
                      ['Shadow Reports', v5Comparison?.is_meaningful ? 'Analyzed' : 'Generating', ''],
                      ['Gate Rescue', `${v5GateReport?.metrics?.rescue_rate ?? 0}%`, ''],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-[1.3rem] border border-stone-900/8 bg-white p-4">
                        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                        <p className="mt-2 text-lg font-semibold leading-6 text-stone-950">{value}</p>
                      </div>
                    ))}
                  </div>
                  {v5Comparison?.is_meaningful && (
                    <div className="rounded-[1rem] border border-stone-900/8 bg-stone-50 p-4 mt-2 mb-2 text-sm text-stone-700">
                      <strong>Shadow Evaluation (Last {v5Comparison?.report?.decision_count ?? '--'} Signals): </strong> V5 Win Rate is {v5Comparison?.report?.v5_win_rate_pct ?? '--'}% vs V4's {v5Comparison?.report?.v4_win_rate_pct ?? '--'}%.
                    </div>
                  )}
                </section>
                
        <section className="mb-6 rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Failure Intelligence</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">What is failing most, and what to change next</h2>
              <p className="text-sm leading-6 text-stone-500">Real failure classifications from the Python backend, ranked into operator-facing weakness signals.</p>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge label={`${formatNumber(weaknessProfile.profile?.total_losses_analyzed, 0)} analyzed losses`} tone={toNumber(weaknessProfile.profile?.total_losses_analyzed) > 0 ? 'warn' : 'neutral'} />
              <button
                type="button"
                onClick={() => {
                  void failuresQuery.refetch()
                  void failureSummaryQuery.refetch()
                  void weaknessQuery.refetch()
                }}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
              >
                <RefreshCw className="h-4 w-4" strokeWidth={1.8} />
                Refresh Weakness
              </button>
            </div>
          </div>

          {toNumber(weaknessProfile.profile?.total_losses_analyzed) <= 0 ? (
            <EmptyState message="No losses have been analyzed yet. Once losing trades are classified, failure counts and ranked improvements will appear here." />
          ) : (
            <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
              <div className="grid gap-4">
                <div className="grid gap-3 md:grid-cols-4">
                  {[
                    ['Total Failures', formatNumber(failureSummary.summary?.total, 0), 'Persisted classified losses.'],
                    ['Avg Severity', formatNumber(failureSummary.summary?.average_severity_score, 2), 'Average severity score across failures.'],
                    ['Avg Confidence', formatNumber((toNumber(failureSummary.summary?.average_confidence) * 100), 1) + '%', 'Classifier confidence across failures.'],
                    ['Top Weakness', `${String(failureSummary.summary?.top_weakness?.failure_source ?? '--')} / ${String(failureSummary.summary?.top_weakness?.blamed_component ?? '--')}`, 'Most frequent weakness pair by count.'],
                  ].map(([label, value, note]) => (
                    <div key={label} className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                      <p className="mt-2 text-lg font-semibold leading-6 text-stone-950">{value}</p>
                      <p className="mt-2 text-sm leading-6 text-stone-500">{note}</p>
                    </div>
                  ))}
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Failure Source</p>
                    <div className="mt-4 grid gap-3">
                      {failureSourceRows.map(([label, count]) => (
                        <div key={label} className="grid gap-2">
                          <div className="flex items-center justify-between gap-3 text-sm">
                            <span className="font-semibold text-stone-950">{label}</span>
                            <span className="text-stone-600">{formatNumber(count, 0)}</span>
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-stone-950/10">
                            <div className="h-full rounded-full bg-amber-700" style={{ width: `${failureSummary.summary?.total ? (count / failureSummary.summary.total) * 100 : 0}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Blamed Component</p>
                    <div className="mt-4 grid gap-3">
                      {failureComponentRows.map(([label, count]) => (
                        <div key={label} className="grid gap-2">
                          <div className="flex items-center justify-between gap-3 text-sm">
                            <span className="font-semibold text-stone-950">{label}</span>
                            <span className="text-stone-600">{formatNumber(count, 0)}</span>
                          </div>
                          <div className="h-2 overflow-hidden rounded-full bg-stone-950/10">
                            <div className="h-full rounded-full bg-rose-700" style={{ width: `${failureSummary.summary?.total ? (count / failureSummary.summary.total) * 100 : 0}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid gap-4">
                <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Severity Distribution</p>
                  <div className="mt-4 grid gap-3">
                    {severityDistribution.map(([score, count]) => (
                      <div key={score} className="grid gap-2">
                        <div className="flex items-center justify-between gap-3 text-sm">
                          <span className="font-semibold text-stone-950">Severity {score}</span>
                          <span className="text-stone-600">{formatNumber(count, 0)}</span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-stone-950/10">
                          <div className="h-full rounded-full bg-stone-950" style={{ width: `${failureRows.length ? (count / failureRows.length) * 100 : 0}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Top Improvements</p>
                  <div className="mt-4 grid gap-3">
                    {topImprovements.length ? topImprovements.map((item, index) => (
                      <div key={`${item.source}-${index}`} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3">
                        <p className="text-sm font-semibold text-stone-950">{item.source}</p>
                        <p className="mt-1 text-sm leading-6 text-stone-600">{item.suggestion}</p>
                      </div>
                    )) : (
                      <div className="rounded-[1rem] border border-dashed border-stone-900/12 px-4 py-4 text-sm text-stone-500">
                        No ranked improvement suggestions are available yet.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Circuit Breaker</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Autonomous trading safety gate</h2>
              <p className="text-sm leading-6 text-stone-500">Trips when recent losses, failure rate, or severity spike beyond configured thresholds for the selected profile.</p>
              <p className="text-xs text-stone-400">Viewing profile: {circuitProfileId}</p>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <label className="grid gap-1 text-xs text-stone-500">
                <span>Circuit profile</span>
                <select
                  value={circuitProfileScope}
                  onChange={(event) => handleCircuitProfileScopeChange(event.target.value)}
                  className="h-10 min-w-[12rem] rounded-xl border border-stone-900/8 bg-white px-3 text-sm text-stone-900"
                >
                  {profileScopeOptions.filter((option) => option.enabled && option.kind === 'profile').map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <StatusBadge
                label={String(circuitState.status ?? 'CLOSED')}
                tone={String(circuitState.status ?? 'CLOSED') === 'OPEN' ? 'bad' : String(circuitState.status ?? 'CLOSED') === 'DEGRADED' ? 'warn' : 'good'}
              />
              <StatusBadge
                label={Boolean(circuitState.enabled ?? true) ? 'Enabled' : 'Disabled'}
                tone={Boolean(circuitState.enabled ?? true) ? 'neutral' : 'warn'}
              />
              {Boolean(circuitState.is_manual_override) ? (
                <StatusBadge
                  label={`Override ${String(circuitState.manual_mode ?? 'AUTO')}`}
                  tone={String(circuitState.manual_mode ?? '') === 'FORCE_OPEN' ? 'bad' : 'warn'}
                />
              ) : null}
              {String(circuitState.status ?? 'CLOSED') === 'OPEN' ? (
                <button
                  type="button"
                  onClick={() => resetCircuitMutation.mutate()}
                  className="inline-flex items-center gap-2 rounded-full border border-rose-900/10 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100"
                >
                  <RefreshCw className="h-4 w-4" strokeWidth={1.8} />
                  Manual reset
                </button>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            {[
              ['Failure Rate', `${formatNumber(circuitState.failure_rate, 1)}%`, 'Rolling recent loss rate.'],
              ['Consecutive Losses', formatNumber(circuitState.consecutive_losses, 0), 'Current uninterrupted loss streak.'],
              ['Auto Resume', formatTime(circuitState.auto_resume_at), 'Cooldown release time when OPEN.'],
              ['Triggered', formatTime(circuitState.triggered_at), 'Last evaluated trip timestamp.'],
              ['Manual Mode', String(circuitState.manual_mode ?? 'AUTO'), 'AUTO evaluates recent results. FORCE_OPEN and FORCE_CLOSED override runtime safety state.'],
              ['Enabled', Boolean(circuitState.enabled ?? true) ? 'Yes' : 'No', 'If disabled, the breaker does not block autonomous scans at all.'],
            ].map(([label, value, note]) => (
              <div key={label} className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                <p className="mt-2 text-lg font-semibold leading-6 text-stone-950">{value}</p>
                <p className="mt-2 text-sm leading-6 text-stone-500">{note}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Current Reason</p>
              <p className="mt-2 text-sm leading-6 text-stone-700">{String(circuitState.reason ?? 'Trading conditions are within configured thresholds.')}</p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-stone-500">
                {(circuitState.active_rules ?? []).map((rule) => (
                  <span key={rule} className="rounded-full bg-stone-950/[0.03] px-3 py-1.5">{rule}</span>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => updateCircuitSettingsMutation.mutate({ CIRCUIT_BREAKER_ENABLED: 'true', CIRCUIT_BREAKER_MANUAL_MODE: 'AUTO' })}
                  disabled={updateCircuitSettingsMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                >
                  Auto
                </button>
                <button
                  type="button"
                  onClick={() => updateCircuitSettingsMutation.mutate({ CIRCUIT_BREAKER_ENABLED: 'true', CIRCUIT_BREAKER_MANUAL_MODE: 'FORCE_OPEN' })}
                  disabled={updateCircuitSettingsMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-full border border-rose-900/10 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100 disabled:opacity-60"
                >
                  Force Open
                </button>
                <button
                  type="button"
                  onClick={() => updateCircuitSettingsMutation.mutate({ CIRCUIT_BREAKER_ENABLED: 'true', CIRCUIT_BREAKER_MANUAL_MODE: 'FORCE_CLOSED' })}
                  disabled={updateCircuitSettingsMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-full border border-amber-900/10 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-900 transition hover:bg-amber-100 disabled:opacity-60"
                >
                  Force Closed
                </button>
                <button
                  type="button"
                  onClick={() => updateCircuitSettingsMutation.mutate({ CIRCUIT_BREAKER_ENABLED: 'false', CIRCUIT_BREAKER_MANUAL_MODE: 'AUTO' })}
                  disabled={updateCircuitSettingsMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-700 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                >
                  Disable
                </button>
              </div>
            </div>
            <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Recent Trips</p>
              <div className="mt-3 grid gap-3">
                {circuitEvents.length ? circuitEvents.slice(0, 4).map((event) => (
                  <div key={`${String(event.id ?? event.triggered_at_utc ?? 'event')}`} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-semibold text-stone-950">{String(event.status ?? '--')}</span>
                      <span className="text-stone-500">{formatTime(event.triggered_at_utc)}</span>
                    </div>
                    <p className="mt-2 leading-6 text-stone-600">{String(event.reason ?? '--')}</p>
                  </div>
                )) : (
                  <p className="text-sm text-stone-500">No circuit breaker events have been persisted yet.</p>
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Learning Status</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Adaptive execution adjustments from recent failures</h2>
              <p className="text-sm leading-6 text-stone-500">This shows whether the analyzer is actively widening stops, penalizing weak entries, and recalibrating confidence from real outcomes.</p>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge
                label={learningStatusLabel}
                tone={!learningEngineEnabled ? 'bad' : (learningPayload.active ? 'warn' : 'neutral')}
              />
              <button
                type="button"
                onClick={() => {
                  updateSettingsMutation.mutate(
                    { LEARNING_ENGINE_ENABLED: learningEngineEnabled ? 'false' : 'true' },
                    {
                      onSuccess: async () => {
                        await Promise.all([
                          settingsQuery.refetch(),
                          learningQuery.refetch(),
                          learningEffectivenessQuery.refetch(),
                        ])
                      },
                    },
                  )
                }}
                disabled={updateSettingsMutation.isPending}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {learningEngineEnabled ? <Pause className="h-4 w-4" strokeWidth={1.8} /> : <Play className="h-4 w-4" strokeWidth={1.8} />}
                {learningEngineEnabled ? 'Disable Learning' : 'Enable Learning'}
              </button>
              <button
                type="button"
                onClick={() => {
                  void learningQuery.refetch()
                  void learningEffectivenessQuery.refetch()
                }}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
              >
                <RefreshCw className="h-4 w-4" strokeWidth={1.8} />
                Refresh Learning
              </button>
              <button
                type="button"
                onClick={async () => {
                  try {
                    const csv = await exportLearningCsv(learningLookbackDays, learningMinConfidence, learningMinSamples)
                    downloadFile(csv, exportFilename('learning', 'csv'), 'text/csv;charset=utf-8')
                    toast.success('Learning CSV downloaded.')
                  } catch (error) {
                    toast.error(error instanceof Error ? error.message : 'Failed to export learning CSV.')
                  }
                }}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
              >
                <BarChart3 className="h-4 w-4" strokeWidth={1.8} />
                Export CSV
              </button>
            </div>
          </div>

          {!learningProfile.samples?.total_closed_trades ? (
            <EmptyState message="Learning stays inactive until enough closed trades and analyzed losses exist." />
          ) : (
            <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
              <div className="grid gap-4">
                <div className="grid gap-3 md:grid-cols-4">
                  {[
                    ['Closed Trades', formatNumber(learningProfile.samples?.total_closed_trades, 0), 'Total closed trades available for calibration.'],
                    ['Analyzed Losses', formatNumber(learningProfile.samples?.analyzed_losses, 0), 'Losses with persisted failure classification.'],
                    ['Top Stop Multiplier', `x${formatNumber(learningProfile.stop_loss_adjustments?.base_multiplier ?? 1, 2)}`, 'Adaptive stop base multiplier from learning.'],
                    ['Last Update', formatTime(learningProfile.generated_at), 'Last profile refresh timestamp.'],
                  ].map(([label, value, note]) => (
                    <div key={label} className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                      <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                      <p className="mt-2 text-lg font-semibold leading-6 text-stone-950">{value}</p>
                      <p className="mt-2 text-sm leading-6 text-stone-500">{note}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                  <div className="flex items-center gap-2">
                    <BarChart3 className="h-4 w-4 text-teal-900" strokeWidth={1.8} />
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Confidence Calibration</p>
                  </div>
                  <div className="mt-4 grid gap-3">
                    {calibrationBuckets.length ? calibrationBuckets.map((bucket) => {
                      const predicted = toNumber(bucket.avg_predicted_confidence, 0) * 100
                      const realized = toNumber(bucket.realized_win_rate, 0) * 100
                      return (
                        <div key={String(bucket.label ?? '--')} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-sm font-semibold text-stone-950">{String(bucket.label ?? '--')}%</span>
                            <span className="text-xs text-stone-500">{formatNumber(bucket.sample_size, 0)} trades</span>
                          </div>
                          <div className="mt-3 grid gap-2">
                            <div>
                              <div className="mb-1 flex items-center justify-between text-xs text-stone-500">
                                <span>Predicted</span>
                                <span>{formatNumber(predicted, 1)}%</span>
                              </div>
                              <div className="h-2 overflow-hidden rounded-full bg-stone-950/10">
                                <div className="h-full rounded-full bg-stone-500" style={{ width: `${predicted}%` }} />
                              </div>
                            </div>
                            <div>
                              <div className="mb-1 flex items-center justify-between text-xs text-stone-500">
                                <span>Realized</span>
                                <span>{formatNumber(realized, 1)}%</span>
                              </div>
                              <div className="h-2 overflow-hidden rounded-full bg-stone-950/10">
                                <div className="h-full rounded-full bg-teal-800" style={{ width: `${realized}%` }} />
                              </div>
                            </div>
                          </div>
                        </div>
                      )
                    }) : (
                      <div className="rounded-[1rem] border border-dashed border-stone-900/12 px-4 py-4 text-sm text-stone-500">
                        Calibration buckets appear once enough closed trades exist across confidence ranges.
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="grid gap-4">
                <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Active Adjustments</p>
                  <div className="mt-4 grid gap-3">
                    {[
                      ['Confidence Calibration', learningProfile.active_adjustments?.confidence_calibration],
                      ['Entry Penalty', learningProfile.active_adjustments?.entry_penalty],
                      ['Adaptive Stop', learningProfile.active_adjustments?.stop_loss_adjustment],
                      ['Component Penalties', learningProfile.active_adjustments?.component_penalties],
                      ['Hard Rejection', learningProfile.active_adjustments?.hard_rejection],
                    ].map(([label, active]) => (
                      <div key={String(label)} className="flex items-center justify-between gap-3 rounded-[1rem] bg-stone-950/[0.03] px-4 py-3">
                        <span className="text-sm font-semibold text-stone-950">{label}</span>
                        <StatusBadge label={active ? 'Active' : 'Inactive'} tone={active ? 'warn' : 'neutral'} />
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Top Penalties</p>
                  <div className="mt-4 grid gap-3">
                    {topLearningPenalties.length ? topLearningPenalties.map((item, index) => (
                      <div key={`${String(item.label ?? item.component ?? 'penalty')}-${index}`} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-sm font-semibold text-stone-950">{String(item.label ?? item.component ?? '--')}</span>
                          <span className="text-xs text-stone-500">{formatNumber(item.penalty, 3)}</span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-3 text-xs text-stone-500">
                          {item.count != null ? <span>{formatNumber(item.count, 0)} failures</span> : null}
                          {item.avg_severity != null ? <span>avg sev {formatNumber(item.avg_severity, 2)}</span> : null}
                          {item.top_failure_source ? <span>{String(item.top_failure_source)}</span> : null}
                          {item.kind ? <span>{String(item.kind)}</span> : null}
                        </div>
                      </div>
                    )) : (
                      <div className="rounded-[1rem] border border-dashed border-stone-900/12 px-4 py-4 text-sm text-stone-500">
                        Penalties will appear here once the failure dataset is large enough to activate learning safely.
                      </div>
                    )}
                  </div>
                </div>

                <div className="rounded-[1.3rem] border border-stone-900/8 bg-white/90 p-4">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Adjustment Effectiveness</p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-stone-500">
                    <span className="rounded-full bg-stone-950/[0.03] px-3 py-1.5">Health {formatNumber(learningEffectiveness?.overall_health_score ?? learningEffectiveness?.health_score, 2)}</span>
                    <span className="rounded-full bg-stone-950/[0.03] px-3 py-1.5">Improving {formatNumber(learningEffectiveness?.status_counts?.IMPROVING, 0)}</span>
                    <span className="rounded-full bg-stone-950/[0.03] px-3 py-1.5">Degrading {formatNumber(learningEffectiveness?.status_counts?.DEGRADING, 0)}</span>
                  </div>
                  <div className="mt-4 grid gap-3">
                    {Array.isArray(learningEffectiveness?.adjustments) && learningEffectiveness.adjustments.length ? learningEffectiveness.adjustments.map((row) => {
                      const status = String(row.status ?? 'INSUFFICIENT_DATA')
                      const tone =
                        status === 'IMPROVING' ? 'good' :
                          status === 'DEGRADING' ? 'bad' :
                            status === 'NEUTRAL' ? 'warn' : 'neutral'
                      return (
                        <div key={String(row.adjustment_id ?? row.label ?? '--')} className="rounded-[1rem] bg-stone-950/[0.03] px-4 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-sm font-semibold text-stone-950">{String(row.label ?? '--')}</span>
                            <StatusBadge label={status} tone={tone} />
                          </div>
                          <div className="mt-2 flex flex-wrap gap-3 text-xs text-stone-500">
                            <span>Before {formatNumber((Number(row.win_rate_before ?? 0) * 100), 1)}%</span>
                            <span>After {formatNumber((Number(row.win_rate_after ?? 0) * 100), 1)}%</span>
                            <span>{formatNumber(row.trades_before, 0)} before</span>
                            <span>{formatNumber(row.trades_after, 0)} after</span>
                          </div>
                          {row.status_reason ? <p className="mt-2 text-xs leading-5 text-stone-500">{String(row.status_reason)}</p> : null}
                        </div>
                      )
                    }) : (
                      <div className="rounded-[1rem] border border-dashed border-stone-900/12 px-4 py-4 text-sm text-stone-500">
                        Effectiveness status will appear once enough adjusted and baseline trades exist.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>

              </>
            ) : null}

            {activeTab === 'alerts' ? (
              <>

        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Operator Alerts</p>
              <h2 className="mt-1 text-xl font-semibold tracking-[-0.04em] text-stone-950">Live backend alerts</h2>
            </div>
            <StatusBadge
              label={`${operatorAlerts.length} active`}
              tone={operatorAlerts.some((item) => String(item.severity ?? '').toLowerCase() === 'critical') ? 'bad' : operatorAlerts.length ? 'warn' : 'good'}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {operatorAlerts.length ? operatorAlerts.map((item, index) => (
              <div
                key={`${String(item.alert_id ?? item.kind ?? index)}-${String(item.detected_at_utc ?? '')}`}
                className={`rounded-[1.25rem] border p-4 ${alertToneClasses(String(item.severity ?? 'info'))}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold uppercase tracking-[0.14em]">{String(item.kind ?? 'alert')}</p>
                  <span className="text-xs font-mono opacity-75">{formatTime(item.detected_at_utc)}</span>
                </div>
                <p className="mt-2 text-sm font-semibold">{String(item.scope ?? 'runtime')}</p>
                <p className="mt-2 text-sm leading-6">{String(item.message ?? '')}</p>
              </div>
            )) : (
              <div className="md:col-span-2">
                <EmptyState message="No operator alerts are active." />
              </div>
            )}
          </div>
        </section>

        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="grid gap-1">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Calibration Readiness</p>
              <h2 className="text-xl font-semibold tracking-[-0.04em] text-stone-950">Probability training coverage by regime and mode</h2>
              <p className="text-sm leading-6 text-stone-500">
                Calibration cannot move until labeled outcomes accumulate. This shows exactly where the analyzer has enough closed trades to train against.
              </p>
            </div>
            <StatusBadge
              label={`${formatNumber(calibrationSummary.ready_scope_count, 0)} scopes ready`}
              tone={toNumber(calibrationSummary.ready_scope_count) > 0 ? 'good' : 'warn'}
            />
          </div>

          <div className="grid gap-3 md:grid-cols-4">
            {[
              ['Total Signals', formatNumber(calibrationSummary.total_signals, 0), 'All persisted signal rows.'],
              ['Labeled Outcomes', formatNumber(calibrationSummary.total_labeled, 0), 'Closed trades available for learning.'],
              ['Threshold', formatNumber(calibrationSummary.calibration_threshold, 0), 'Target per regime and mode scope.'],
              ['Ready Scopes', formatNumber(calibrationSummary.ready_scope_count, 0), 'Scopes ready for calibration work.'],
            ].map(([label, value, note]) => (
              <div key={label} className="rounded-[1.35rem] border border-stone-900/8 bg-white/90 p-4">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                <p className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-stone-950">{value}</p>
                <p className="mt-2 text-sm leading-6 text-stone-500">{note}</p>
              </div>
            ))}
          </div>

          <div className="mt-4 overflow-x-auto rounded-[1.35rem] border border-stone-900/8 bg-white/92">
            <table className="min-w-full divide-y divide-stone-900/8 text-sm">
              <thead className="bg-stone-950/[0.03] text-stone-600">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Regime</th>
                  <th className="px-4 py-3 text-left font-medium">Mode</th>
                  <th className="px-4 py-3 text-right font-medium">Total</th>
                  <th className="px-4 py-3 text-right font-medium">Labeled</th>
                  <th className="px-4 py-3 text-right font-medium">Avg Win R</th>
                  <th className="px-4 py-3 text-right font-medium">Avg Loss R</th>
                  <th className="px-4 py-3 text-right font-medium">Remaining</th>
                  <th className="px-4 py-3 text-right font-medium">Ready</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-900/8">
                {calibrationScopes.length ? (
                  calibrationScopes.map((scope) => (
                    <tr key={`${scope.regime ?? 'UNKNOWN'}-${scope.mode ?? 'UNKNOWN'}`}>
                      <td className="px-4 py-3 text-stone-900">{scope.regime ?? 'UNKNOWN'}</td>
                      <td className="px-4 py-3 text-stone-900">{scope.mode ?? 'UNKNOWN'}</td>
                      <td className="px-4 py-3 text-right text-stone-700">{formatNumber(scope.total, 0)}</td>
                      <td className="px-4 py-3 text-right font-semibold text-stone-950">{formatNumber(scope.labeled, 0)}</td>
                      <td className="px-4 py-3 text-right text-teal-900">{scope.avg_win_r == null ? '—' : formatNumber(scope.avg_win_r, 2)}</td>
                      <td className="px-4 py-3 text-right text-rose-800">{scope.avg_loss_r == null ? '—' : formatNumber(scope.avg_loss_r, 2)}</td>
                      <td className="px-4 py-3 text-right text-stone-700">{formatNumber(scope.remaining_to_threshold, 0)}</td>
                      <td className="px-4 py-3 text-right">
                        <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${scope.ready_for_calibration ? 'bg-teal-900 text-stone-50' : 'bg-amber-100 text-amber-900'}`}>
                          <BrainCircuit className="h-3.5 w-3.5" strokeWidth={1.8} />
                          {scope.ready_for_calibration ? 'Ready' : 'Collecting'}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="px-4 py-8">
                      <EmptyState message="Signals are being stored, but closed trades have not accumulated enough labeled outcomes to show calibration progress." />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

              </>
            ) : null}

            {activeTab === 'budget' ? (
              <>

        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Paper Budget</p>
              <h2 className="mt-1 text-xl font-semibold tracking-[-0.04em] text-stone-950">Live paper cash and default budget</h2>
            </div>
            <StatusBadge
              label={`$${formatNumber(paperBalance.balance, 2)} available`}
              tone={toNumber(paperBalance.balance) > 0 ? 'good' : 'bad'}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              {[
                ['Available Cash', `$${formatNumber(paperBalance.balance, 2)}`, 'Current free paper money for new trades.'],
                ['Default Budget', `$${formatNumber(paperBalance.default_balance, 2)}`, 'Reset target and initial account balance.'],
                ['Account Scope', String(paperBalance.account?.account_key ?? 'default'), 'Single-operator paper account used by v4.'],
                ['Legacy Reserved', `$${formatNumber(reconciliation.total_reserved_cost, 2)}`, 'Capital reserved by the latest legacy-trade reconciliation run.'],
              ].map(([label, value, note]) => (
                <div key={label} className="rounded-[1.25rem] border border-stone-900/8 bg-white/90 p-4">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                  <p className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-stone-950">{value}</p>
                  <p className="mt-2 text-sm leading-6 text-stone-500">{note}</p>
                </div>
              ))}
            </div>

            <div className="grid gap-3 rounded-[1.35rem] bg-stone-950/[0.03] p-4">
              <div className="rounded-[1rem] bg-white px-4 py-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                <p className="text-sm font-semibold text-stone-950">Deposit paper funds</p>
                <p className="mt-1 text-sm text-stone-500">Use this when you want to top up the current paper account without resetting history.</p>
                <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={paperDepositDraft}
                    onChange={(event) => setPaperDepositDraft(event.target.value)}
                    className="h-11 w-full rounded-2xl border border-stone-900/8 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
                  />
                  <button
                    type="button"
                    onClick={() => depositMutation.mutate(Number(paperDepositDraft))}
                    disabled={depositMutation.isPending || Number(paperDepositDraft) <= 0}
                    className="rounded-full bg-stone-950 px-4 py-2.5 text-sm font-semibold text-stone-50 transition hover:bg-stone-900 disabled:opacity-60"
                  >
                    {depositMutation.isPending ? 'Depositing…' : 'Deposit'}
                  </button>
                </div>
              </div>

              <div className="rounded-[1rem] bg-white px-4 py-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                <p className="text-sm font-semibold text-stone-950">Reset paper balance</p>
                <p className="mt-1 text-sm text-stone-500">
                  Reset sets the live account back to the current default budget. Open paper orders must be closed first.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => resetPaperMutation.mutate(undefined)}
                    disabled={resetPaperMutation.isPending}
                    className="rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                  >
                    {resetPaperMutation.isPending ? 'Resetting…' : 'Reset To Default'}
                  </button>
                  <span className="rounded-full bg-stone-950/[0.03] px-3 py-2 text-sm text-stone-600">
                    Target ${formatNumber(settingsDraft.PAPER_DEFAULT_BALANCE ?? settings.PAPER_DEFAULT_BALANCE, 2)}
                  </span>
                </div>
              </div>

              <div className="rounded-[1rem] bg-white px-4 py-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                <p className="text-sm font-semibold text-stone-950">Reconcile legacy open trades</p>
                <p className="mt-1 text-sm text-stone-500">
                  Backfill reserved capital for paper orders that were opened before budget tracking existed. This only touches still-open orders that never reserved cash.
                </p>
                <div className="mt-3 flex flex-wrap gap-2 text-sm text-stone-600">
                  <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">
                    Reconciled {formatNumber(reconciliation.reconciled_orders, 0)}
                  </span>
                  <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">
                    Already tracked {formatNumber(reconciliation.already_reconciled, 0)}
                  </span>
                  <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">
                    Deficit ${formatNumber(reconciliation.deficit, 2)}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => reconcilePaperMutation.mutate()}
                    disabled={reconcilePaperMutation.isPending}
                    className="rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                  >
                    {reconcilePaperMutation.isPending ? 'Reconciling…' : 'Run Reconciliation'}
                  </button>
                  <span className="text-sm text-stone-500">
                    Starting ${formatNumber(reconciliation.starting_balance, 2)} → ending ${formatNumber(reconciliation.ending_balance, 2)}
                  </span>
                </div>
              </div>

              <div className="rounded-[1rem] bg-white px-4 py-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                <p className="text-sm font-semibold text-stone-950">Confidence sizing curve</p>
                <p className="mt-1 text-sm text-stone-500">
                  Auto paper trades now scale notional by confidence instead of assuming the same size for every signal.
                </p>
                <div className="mt-4 grid gap-4">
                  {[
                    ['PAPER_POSITION_SIZE_MIN_PCT', 'Minimum allocation %'],
                    ['PAPER_POSITION_SIZE_MAX_PCT', 'Maximum allocation %'],
                    ['PAPER_POSITION_CONFIDENCE_FLOOR', 'Confidence floor'],
                    ['PAPER_POSITION_CONFIDENCE_CEIL', 'Confidence ceiling'],
                  ].map(([key, label]) => (
                    <div key={key} className="grid gap-2">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm font-semibold text-stone-900">{label}</span>
                        <span className="text-sm text-stone-500">{settingsDraft[key]}{key.includes('PCT') ? '%' : ''}</span>
                      </div>
                      <div className="grid grid-cols-[1fr_84px] gap-3">
                        <input
                          type="range"
                          min={key.includes('PCT') ? 0 : 0}
                          max={100}
                          step={key.includes('PCT') ? 0.5 : 1}
                          value={settingsDraft[key] ?? settings[key] ?? ''}
                          onChange={(event) => setDraftValue(key, event.target.value)}
                        />
                        <input
                          type="number"
                          min={0}
                          max={100}
                          step={key.includes('PCT') ? 0.5 : 1}
                          value={settingsDraft[key] ?? settings[key] ?? ''}
                          onChange={(event) => setDraftValue(key, event.target.value)}
                          className="h-10 rounded-2xl border border-stone-900/8 bg-white px-3 text-sm text-stone-900 outline-none transition focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 rounded-[1rem] bg-stone-950/[0.03] p-3">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Live preview on ${formatNumber(paperBalance.balance, 2)} free cash</p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    {sizingPreviewRows.map((row) => (
                      <div key={row.confidence} className="rounded-[0.95rem] bg-white px-3 py-3">
                        <p className="text-sm font-semibold text-stone-950">{row.confidence}% confidence</p>
                        <p className="mt-1 text-sm text-stone-500">{formatNumber(row.allocationPct, 2)}% allocation</p>
                        <p className="mt-2 text-lg font-semibold tracking-[-0.04em] text-stone-950">${formatNumber(row.notional, 2)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

              </>
            ) : null}

            {activeTab === 'settings' ? (
              <>

        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="mb-4 flex items-center gap-3">
            <Settings2 className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Runtime Configuration</p>
              <h2 className="mt-1 text-xl font-semibold tracking-[-0.04em] text-stone-950">Edit the settings currently steering engine behavior</h2>
            </div>
          </div>
          <div className="grid gap-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {settingsOverviewCards.map(([label, value]) => (
                <div key={label} className="rounded-[1.2rem] border border-stone-900/8 bg-white/90 p-4">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                  <p className="mt-2 text-xl font-semibold tracking-[-0.04em] text-stone-950">{value}</p>
                </div>
              ))}
            </div>

            <div className="rounded-[1.35rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Learning Presets</p>
                  <p className="mt-1 text-sm text-stone-500">Quick-apply operating modes for the learning stack without editing individual flags.</p>
                </div>
                <span className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-stone-600 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                  {activeLearningPresetId ? LEARNING_PRESETS.find((preset) => preset.id === activeLearningPresetId)?.label : 'Custom mix'}
                </span>
              </div>
              <div className="grid gap-3 lg:grid-cols-3">
                {LEARNING_PRESETS.map((preset) => {
                  const active = preset.id === activeLearningPresetId
                  return (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => applyLearningPreset(preset.values)}
                      className={`rounded-[1.1rem] border px-4 py-4 text-left transition-[transform,box-shadow,border-color,background-color] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-0.5 ${
                        active
                          ? 'border-teal-900/12 bg-white shadow-[0_18px_30px_rgba(20,83,45,0.08)]'
                          : 'border-stone-900/8 bg-white/80'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-stone-950">{preset.label}</p>
                        <StatusBadge label={active ? 'Selected' : 'Preset'} tone={active ? 'good' : 'neutral'} />
                      </div>
                      <p className="mt-2 text-sm leading-6 text-stone-500">{preset.description}</p>
                      <div className="mt-3 grid gap-1 text-xs text-stone-500">
                        <span>Engine: {preset.values.LEARNING_ENGINE_ENABLED}</span>
                        <span>Calibration: {preset.values.LEARNING_CALIBRATION_ENABLED}</span>
                        <span>Adaptive stop: {preset.values.LEARNING_ADAPTIVE_STOP_ENABLED}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="rounded-[1.35rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Strategy Mode Roster</p>
                  <p className="mt-1 text-sm text-stone-500">Visibility is fixed here so disabled modes do not disappear from the operator surface.</p>
                </div>
                <span className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-stone-600 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                  {formatNumber(enabledModes.length, 0)} enabled
                </span>
              </div>
              <div className="grid gap-3 lg:grid-cols-3">
                {STRATEGY_MODE_CATALOG.map((mode) => {
                  const active = selectedModeSet.has(mode.value)
                  return (
                    <button
                      key={mode.value}
                      type="button"
                      onClick={() => toggleCsvItem('AUTONOMOUS_MODES', mode.value)}
                      className={`text-left rounded-[1.1rem] border px-4 py-4 transition-[transform,box-shadow,border-color,background-color] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-0.5 ${
                        active
                          ? 'border-teal-900/12 bg-white shadow-[0_18px_30px_rgba(20,83,45,0.08)]'
                          : 'border-stone-900/8 bg-white/70'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-stone-950">{mode.label}</p>
                        <StatusBadge label={active ? 'Enabled' : 'Disabled'} tone={active ? 'good' : 'neutral'} />
                      </div>
                      <p className="mt-2 text-sm leading-6 text-stone-500">{mode.description}</p>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="rounded-[1.35rem] border border-stone-900/8 bg-stone-950/[0.03] p-4">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Mode Interval Policy</p>
                  <p className="mt-1 text-sm text-stone-500">Define which intervals each strategy mode is allowed to analyze. Disallowed combinations are skipped in autonomous and queued scans.</p>
                </div>
                <span className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-stone-600 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                  {formatNumber(globalIntervalSet.size, 0)} global intervals
                </span>
              </div>

              <div className="mb-4 grid gap-3 lg:grid-cols-3">
                {STRATEGY_MODE_CATALOG.map((mode) => (
                  <div key={`${mode.value}-recommended`} className="rounded-[1rem] border border-stone-900/8 bg-white/90 px-4 py-3 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                    <p className="text-[0.68rem] uppercase tracking-[0.16em] text-stone-500">{mode.label} recommended</p>
                    <p className="mt-2 text-sm font-semibold text-stone-950">{mode.recommendedIntervals.join(', ')}</p>
                    <p className="mt-1 text-xs text-stone-500">{mode.description}</p>
                  </div>
                ))}
              </div>

              <div className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {modePolicySummaryCards.map(([label, value]) => (
                  <div key={label} className="rounded-[1rem] bg-white/90 px-4 py-3 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                    <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                    <p className="mt-2 text-sm font-semibold text-stone-950">{value}</p>
                  </div>
                ))}
              </div>

              <div className="grid gap-3 xl:grid-cols-3">
                {modeIntervalRows.map((mode) => (
                  <div
                    key={mode.value}
                    className={`rounded-[1.1rem] border px-4 py-4 transition-[border-color,background-color,box-shadow] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
                      mode.enabled
                        ? 'border-teal-900/12 bg-white shadow-[0_18px_30px_rgba(20,83,45,0.08)]'
                        : 'border-stone-900/8 bg-white/80'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-stone-950">{mode.label}</p>
                        <p className="mt-1 text-sm text-stone-500">{settingHint(mode.key)}</p>
                        <p className="mt-1 text-xs text-stone-500">Recommended: {mode.recommendedIntervals.join(', ')}</p>
                      </div>
                      <StatusBadge label={mode.enabled ? 'Enabled' : 'Disabled'} tone={mode.enabled ? 'good' : 'neutral'} />
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {availableIntervals.map((interval) => {
                        const selected = mode.selected.includes(interval)
                        const disabled = !globalIntervalSet.has(interval)
                        return (
                          <button
                            key={`${mode.value}-${interval}`}
                            type="button"
                            onClick={() => toggleCsvItem(mode.key, interval)}
                            disabled={disabled}
                            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                              selected
                                ? 'theme-active-chip'
                                : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                            } ${disabled ? 'cursor-not-allowed opacity-45' : ''}`}
                          >
                            {interval}
                          </button>
                        )
                      })}
                    </div>
                    <p className="mt-3 text-xs text-stone-500">
                      {mode.selected.length
                        ? `Allowed: ${mode.selected.join(', ')}`
                        : 'No mode-specific interval selected. The engine will fall back to the global interval set.'}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {settingsDirty ? (
              <div className="flex flex-col gap-3 rounded-[1.35rem] border border-amber-900/10 bg-amber-50/80 p-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="grid gap-1">
                  <p className="text-sm font-semibold text-amber-900">Unsaved changes</p>
                  <p className="text-sm text-amber-900/80">Update values here and apply them directly to the live engine.</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setSettingsDraft(settings)}
                    disabled={updateSettingsMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                  >
                    Discard
                  </button>
                  <button
                    type="button"
                    onClick={saveRuntimeSettings}
                    disabled={updateSettingsMutation.isPending}
                    className="inline-flex items-center gap-2 rounded-full bg-stone-950 px-4 py-2.5 text-sm font-semibold text-stone-50 transition hover:bg-stone-900 disabled:opacity-60"
                  >
                    {updateSettingsMutation.isPending ? 'Saving…' : 'Apply to engine'}
                  </button>
                </div>
              </div>
            ) : null}

            <div className="grid gap-4">
              {editableGroups.map((group) => (
                <div key={group.title} className="overflow-hidden rounded-[1.35rem] border border-stone-900/8 bg-white">
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.title)}
                    className="flex w-full items-center justify-between px-5 py-4 text-left"
                  >
                    <div className="grid gap-1">
                      <span className="font-semibold text-stone-950">{group.title}</span>
                      <span className="text-sm text-stone-500">{group.items.length} settings</span>
                    </div>
                    <ChevronDown className={`h-4 w-4 text-stone-400 transition-transform ${openGroups[group.title] ? 'rotate-180' : ''}`} strokeWidth={1.8} />
                  </button>
                  {openGroups[group.title] ? (
                    <div className="border-t border-stone-900/8 bg-stone-950/[0.03] p-4">
                      <div className="grid gap-3">
                        {group.items.map((item) => {
                          const value = settingsDraft[item.key] ?? settings[item.key] ?? ''
                          return (
                            <div key={item.key} className="rounded-[1rem] bg-white px-4 py-3 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                              <div className="grid gap-1">
                                <p className="text-sm font-semibold text-stone-950">{item.label}</p>
                                <p className="text-sm text-stone-500">{settingHint(item.key)}</p>
                              </div>

                              {item.type === 'toggle' ? (
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {[
                                    ['true', 'Enabled'],
                                    ['false', 'Disabled'],
                                  ].map(([option, label]) => (
                                    <button
                                      key={option}
                                      type="button"
                                      onClick={() => setDraftValue(item.key, option)}
                                      className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                                        normalizeBooleanSetting(value) === option
                                          ? 'theme-active-chip'
                                          : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                                      }`}
                                    >
                                      {label}
                                    </button>
                                  ))}
                                </div>
                              ) : null}

                              {item.type === 'chips' ? (
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {item.options?.map((option) => (
                                    <button
                                      key={option}
                                      type="button"
                                      onClick={() => setDraftValue(item.key, option)}
                                      className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                                        value === option
                                          ? 'theme-active-chip'
                                          : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                                      }`}
                                    >
                                      {option}
                                    </button>
                                  ))}
                                </div>
                              ) : null}

                              {item.type === 'multi' ? (
                                <>
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {item.options?.map((option) => {
                                      const active = splitCsv(value).includes(option)
                                      return (
                                        <button
                                          key={option}
                                          type="button"
                                          onClick={() => toggleCsvItem(item.key, option)}
                                          className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                                            active
                                              ? 'theme-active-chip'
                                              : 'border border-stone-900/8 bg-white text-stone-700 hover:bg-stone-950/[0.03]'
                                          }`}
                                        >
                                          {option}
                                        </button>
                                      )
                                    })}
                                  </div>
                                  <input
                                    value={value}
                                    onChange={(event) => setDraftValue(item.key, event.target.value)}
                                    className="mt-3 h-11 w-full rounded-2xl border border-stone-900/8 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
                                  />
                                </>
                              ) : null}

                              {item.type === 'number' ? (
                                <>
                                  <input
                                    type="number"
                                    min={item.min}
                                    max={item.max}
                                    step={item.step}
                                    value={value}
                                    onChange={(event) => setDraftValue(item.key, event.target.value)}
                                    className="mt-3 h-11 w-full rounded-2xl border border-stone-900/8 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
                                  />
                                  <p className={`mt-2 text-sm font-semibold ${settingTone(item.key, value)}`}>{value}</p>
                                </>
                              ) : null}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ) : null}
                </div>
              ))}

              <div className="overflow-hidden rounded-[1.35rem] border border-stone-900/8 bg-white">
                <button
                  type="button"
                  onClick={() => toggleGroup('Engine')}
                  className="flex w-full items-center justify-between px-5 py-4 text-left"
                >
                  <div className="grid gap-1">
                    <span className="font-semibold text-stone-950">Engine</span>
                    <span className="text-sm text-stone-500">{groupedSettings.Engine.length} settings</span>
                  </div>
                  <ChevronDown className={`h-4 w-4 text-stone-400 transition-transform ${openGroups.Engine ? 'rotate-180' : ''}`} strokeWidth={1.8} />
                </button>
                {openGroups.Engine ? (
                  <div className="border-t border-stone-900/8 bg-stone-950/[0.03] p-4">
                    <div className="grid gap-3">
                      {groupedSettings.Engine.length ? groupedSettings.Engine.map(([key, value]) => (
                        <div key={key} className="rounded-[1rem] bg-white px-4 py-3 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                          <div className="grid gap-1">
                            <p className="text-sm font-semibold text-stone-950">{prettySettingLabel(key)}</p>
                            <p className="text-sm text-stone-500">{settingHint(key)}</p>
                          </div>
                          <input
                            value={settingsDraft[key] ?? value}
                            onChange={(event) => setDraftValue(key, event.target.value)}
                            className="mt-3 h-11 w-full rounded-2xl border border-stone-900/8 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-teal-900/20 focus:ring-4 focus:ring-teal-900/6"
                          />
                        </div>
                      )) : (
                        <div className="rounded-[1rem] bg-white px-4 py-3 text-sm text-stone-500 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                          No engine settings captured.
                        </div>
                      )}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </section>

	              </>
	            ) : null}

            {activeTab === 'alerts' ? (
              <>
        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="mb-4 flex items-center gap-3">
            <Radar className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Alert Breakdown</p>
              <h2 className="mt-1 text-xl font-semibold tracking-[-0.04em] text-stone-950">Severity and scope totals from the backend</h2>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            {[
              { title: 'By Severity', rows: alertSeverityRows },
              { title: 'By Scope', rows: alertScopeRows },
            ].map((section) => (
              <div key={section.title} className="rounded-[1.35rem] bg-stone-950/[0.03] p-4">
                <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-stone-950">
                  <Radar className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
                  {section.title}
                </div>
                <div className="grid gap-3">
                  {section.rows.length ? section.rows.map(([label, value]) => (
                    <div key={label} className="rounded-[1rem] bg-white px-4 py-3 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-stone-950">{label}</p>
                        <span className="text-sm font-semibold text-teal-900">{formatNumber(value, 0)}</span>
                      </div>
                    </div>
                  )) : (
                    <EmptyState message={`No ${section.title.toLowerCase()} data recorded yet.`} />
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
              </>
            ) : null}
	      </div>
        </section>
      </div>
	    </AnimatedRoute>
	  )
	}
