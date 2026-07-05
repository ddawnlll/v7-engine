import { useCallback, useMemo } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  fetchEngineHealthForScope, fetchJobsForScope, fetchOperatorAlertsForScope,
  fetchPortfolioForScope, fetchRuntimeProfileReadOnlyExposure,
  fetchRuntimeSettingsForScope, fetchSymbols, getCircuitBreakerState,
  pauseScans, resumeScans, stopScans, triggerScanNow,
} from '../lib/api'
import { statusTone } from '../lib/format'
import { queryClient } from '../lib/queryClient'
import { preferLargerSymbolUniverse, splitCsv } from '../lib/helpers'
import type { AlertItem, CircuitBreakerState, OperatorAlertRow } from '../lib/types'

function toneToBadgeTone(tone: string): 'neutral' | 'good' | 'warn' | 'bad' {
  if (tone === 'tone-good') return 'good'
  if (tone === 'tone-warn') return 'warn'
  if (tone === 'tone-bad') return 'bad'
  return 'neutral'
}

function mapAlertRow(alert: OperatorAlertRow): AlertItem {
  const scope = String(alert.scope ?? '').toLowerCase()
  const route = scope === 'exchange' ? '/trade/markets' : scope === 'database' ? '/system/storage' : '/operate/control'
  return {
    id: String(alert.alert_id ?? alert.kind ?? `${scope}-${alert.detected_at_utc ?? 'alert'}`),
    title: String(alert.kind ?? 'operator_alert').replaceAll('_', ' '),
    message: String(alert.message ?? ''),
    severity: String(alert.severity ?? 'info') as AlertItem['severity'],
    route,
    timestamp: alert.detected_at_utc,
    unread: String(alert.severity ?? '').toLowerCase() === 'critical',
  }
}

export type ShellStatus = {
  health: Record<string, unknown> | null
  jobs: Record<string, unknown> | null
  portfolio: Record<string, unknown> | null
  runtimeSettings: Record<string, string>
  engineLabel: string
  engineTone: 'neutral' | 'good' | 'warn' | 'bad'
  engineDetail: string | null
  engineDetailHref: string | null
  queuePending: number
  queueFailed: number
  netR: number
  expectedNetR: number
  circuitBreaker: CircuitBreakerState
  scanControl: Record<string, unknown> | null
  isScanPaused: boolean
  hasActiveScan: boolean
  alerts: AlertItem[]
  error: Error | null
  availableSymbols: string[]
  isRefreshing: boolean
  isRefreshEnabled: boolean

  /** Callback: refetch all shell queries. */
  refresh: () => void

  pauseScans: () => void
  resumeScans: () => void
  stopScans: () => void
  triggerScanNow: () => void
  isPausingScans: boolean
  isResumingScans: boolean
  isStoppingScans: boolean
  isTriggeringScan: boolean
  stopRequested: boolean
}

export function useShellStatusQuery(activeProfileScope: string): ShellStatus {
  const healthQuery = useQuery({
    queryKey: ['engine-health', 'app-shell', activeProfileScope],
    queryFn: () => fetchEngineHealthForScope(activeProfileScope),
    refetchInterval: 10_000,
    refetchOnWindowFocus: false,
  })
  const jobsQuery = useQuery({
    queryKey: ['scan-jobs', 'app-shell', activeProfileScope],
    queryFn: () => fetchJobsForScope(50, activeProfileScope),
    refetchInterval: 10_000,
    refetchOnWindowFocus: false,
  })
  const alertsQuery = useQuery({
    queryKey: ['operator-alerts', 'app-shell', activeProfileScope],
    queryFn: () => fetchOperatorAlertsForScope(activeProfileScope),
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const portfolioQuery = useQuery({
    queryKey: ['portfolio', 'app-shell', activeProfileScope],
    queryFn: async () => {
      if (!activeProfileScope || activeProfileScope === 'paper-main') {
        return fetchPortfolioForScope(activeProfileScope)
      }
      await fetchRuntimeProfileReadOnlyExposure(activeProfileScope)
      return { summary: { net_r: 0, expected_net_r: 0 } }
    },
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const settingsQuery = useQuery({
    queryKey: ['runtime-settings', 'app-shell', activeProfileScope],
    queryFn: () => fetchRuntimeSettingsForScope(activeProfileScope),
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const symbolsQuery = useQuery({
    queryKey: ['symbols', 'app-shell'],
    queryFn: fetchSymbols,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const circuitBreakerQuery = useQuery({
    queryKey: ['circuit-breaker-state', 'app-shell', activeProfileScope],
    queryFn: () => getCircuitBreakerState(10, activeProfileScope),
    refetchInterval: 10_000,
    refetchOnWindowFocus: false,
  })

  const pauseScansMutation = useMutation({
    mutationFn: () => pauseScans('navbar', activeProfileScope),
    onSuccess: async () => {
      toast.success('Scan pause requested')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to pause scans', {
        description: error instanceof Error ? error.message : 'Unknown error',
      })
    },
  })
  const resumeScansMutation = useMutation({
    mutationFn: () => resumeScans('navbar', activeProfileScope),
    onSuccess: async () => {
      toast.success('Scan resume requested')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to resume scans', {
        description: error instanceof Error ? error.message : 'Unknown error',
      })
    },
  })
  const stopScansMutation = useMutation({
    mutationFn: () => stopScans('navbar', activeProfileScope),
    onSuccess: async () => {
      toast.success('Stop requested for active scan')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to stop scan', {
        description: error instanceof Error ? error.message : 'Unknown error',
      })
    },
  })
  const triggerScanMutation = useMutation({
    mutationFn: () => triggerScanNow(activeProfileScope),
    onSuccess: async (payload) => {
      const breaker = (circuitBreakerQuery.data?.state ?? {}) as CircuitBreakerState
      const trigger = (payload.trigger ?? {}) as Record<string, unknown>
      const paused = Boolean(trigger.paused)
      const restartedLoop = Boolean(trigger.restarted_loop)
      const resumedFromPause = Boolean(trigger.resumed_from_pause)
      if (String(breaker.status ?? '').toUpperCase() === 'OPEN') {
        toast('Autonomous scan blocked by circuit breaker', {
          description: breaker.auto_resume_at
            ? `Resumes at ${new Date(breaker.auto_resume_at).toLocaleString()}`
            : String(breaker.reason ?? 'Recent failure conditions require a cooldown.'),
        })
      } else {
        toast.success(resumedFromPause ? 'Scan started after resuming scans' : paused ? 'Scan queued, but the runtime is paused' : 'Next autonomous scan triggered', {
          description: paused
            ? 'Resume scans to let the queued trigger run.'
            : resumedFromPause
              ? 'The scan control was resumed and the autonomous loop was woken.'
              : restartedLoop
                ? 'The autonomous loop was restarted before queuing the trigger.'
                : 'The autonomous loop has been woken for the next scan cycle.',
        })
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'app-shell'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs', 'admin'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
        queryClient.invalidateQueries({ queryKey: ['circuit-breaker-state'] }),
        queryClient.invalidateQueries({ queryKey: ['circuit-breaker-state', 'app-shell'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to trigger autonomous scan', {
        description: error instanceof Error ? error.message : 'Unknown error',
      })
    },
  })

  const health = healthQuery.data ?? null as Record<string, unknown> | null
  const jobs = jobsQuery.data ?? null as Record<string, unknown> | null
  const portfolio = portfolioQuery.data ?? null as Record<string, unknown> | null
  const runtimeSettings = (settingsQuery.data ?? {}) as Record<string, string>
  const engineLabel = String((health as Record<string, unknown> | null)?.status ?? 'unknown')
  const engineTone = toneToBadgeTone(statusTone(engineLabel))
  const alertsData = ((alertsQuery.data as { items?: OperatorAlertRow[] } | null)?.items ?? []) as OperatorAlertRow[]
  const jData = jobs as Record<string, unknown> | null
  const pData = portfolio as Record<string, unknown> | null

  const criticalAlert = ((health as Record<string, unknown> | null)?.alert_summary as Record<string, unknown> | undefined)?.items
    ? ((health as Record<string, unknown> | null)?.alert_summary as Record<string, unknown>)?.items
        ?.find((item: Record<string, unknown>) => String(item?.severity ?? '').toLowerCase() === 'critical')
    : null

  const engineStatusDetail = (() => {
    if (engineLabel.toLowerCase() !== 'degraded') return { detail: null as string | null, href: null as string | null }
    const h = health as Record<string, unknown> | null
    if (h?.db_connected === false) return { detail: 'database disconnected', href: '/operate/control' }
    if (String(h?.degraded_reason ?? '').toLowerCase() === 'last_error') {
      const message = String(((h?.last_error as Record<string, unknown> | null)?.message as string | null) ?? '').trim()
      return { detail: message || 'recent runtime error', href: '/operate/logs' }
    }
    if (Number((h?.alert_summary as Record<string, unknown> | undefined)?.critical ?? 0) > 0) {
      const crit = criticalAlert
      return { detail: String(crit?.message ?? crit?.kind ?? 'critical alert active'), href: '/operate/alerts' }
    }
    if (Number(h?.heartbeat_age_seconds ?? 0) > 180 || String(h?.degraded_reason ?? '') === 'runner_heartbeat_stale') {
      return { detail: `runner heartbeat stale (${Math.round(Number(h?.heartbeat_age_seconds ?? 0))}s)`, href: '/operate/control' }
    }
    const stream = h?.stream as Record<string, unknown> | null | undefined
    if (String(stream?.status ?? '').toUpperCase() === 'DEGRADED') {
      return { detail: String(stream?.error_text ?? 'user data stream degraded'), href: '/operate/control' }
    }
    if (Boolean(stream?.reconnect_required)) {
      return { detail: 'user data stream reconnect required', href: '/operate/control' }
    }
    const reconciliation = h?.reconciliation as Record<string, unknown> | null | undefined
    if (String(reconciliation?.status ?? '').toUpperCase() === 'DEGRADED') {
      return { detail: String(reconciliation?.message ?? 'reconciliation degraded'), href: '/operate/control' }
    }
    const profile = h?.profile as Record<string, unknown> | null | undefined
    const connectivityStatus = String((profile?.connectivity as Record<string, unknown> | undefined)?.status ?? '').toLowerCase()
    if (connectivityStatus === 'error') return { detail: 'profile connectivity error', href: '/operate/config' }
    if (connectivityStatus === 'missing_credentials') return { detail: 'profile credentials missing', href: '/operate/config' }
    return { detail: 'recent runtime error or profile alert', href: '/operate/logs' }
  })()
  const engineDetail = engineStatusDetail.detail
  const engineDetailHref = engineStatusDetail.href

  const queuePending = Number((jData?.pending as number | undefined) ?? 0)
  const queueFailed = Number((jData?.failed as number | undefined) ?? 0)
  const netR = Number(((pData?.summary as Record<string, unknown> | undefined)?.net_r as number | undefined) ?? 0)
  const expectedNetR = Number(((pData?.summary as Record<string, unknown> | undefined)?.expected_net_r as number | undefined) ?? netR)
  const circuitBreaker = ((circuitBreakerQuery.data as Record<string, unknown> | null)?.state ?? {}) as CircuitBreakerState
  const scanControl = (health as Record<string, unknown> | null)?.scan_control as Record<string, unknown> | null ?? null
  const isScanPaused = String((scanControl as Record<string, unknown> | null)?.desired_state ?? '').toUpperCase() === 'PAUSED'
  const hasActiveScan = String((scanControl as Record<string, unknown> | null)?.active_status ?? '').toUpperCase() === 'RUNNING' || Boolean((scanControl as Record<string, unknown> | null)?.active_run_id)
  const alerts = alertsData.map(mapAlertRow)
  const error = [healthQuery.error, jobsQuery.error, alertsQuery.error, portfolioQuery.error, settingsQuery.error, circuitBreakerQuery.error]
    .find((item) => item instanceof Error) ?? null
  const symbolsData = symbolsQuery.data as { symbols?: string[] } | null
  const availableSymbols = preferLargerSymbolUniverse(symbolsData?.symbols, splitCsv(runtimeSettings.AUTONOMOUS_SYMBOLS))
  const isRefreshing = healthQuery.isFetching || jobsQuery.isFetching || alertsQuery.isFetching || portfolioQuery.isFetching || settingsQuery.isFetching || symbolsQuery.isFetching || circuitBreakerQuery.isFetching

  const refresh = useCallback(() => {
    void healthQuery.refetch()
    void jobsQuery.refetch()
    void alertsQuery.refetch()
    void portfolioQuery.refetch()
    void settingsQuery.refetch()
    void symbolsQuery.refetch()
    void circuitBreakerQuery.refetch()
  }, [healthQuery, jobsQuery, alertsQuery, portfolioQuery, settingsQuery, symbolsQuery, circuitBreakerQuery])

  return {
    health,
    jobs,
    portfolio,
    runtimeSettings,
    engineLabel,
    engineTone,
    engineDetail,
    engineDetailHref,
    queuePending,
    queueFailed,
    netR,
    expectedNetR,
    circuitBreaker,
    scanControl,
    isScanPaused,
    hasActiveScan,
    alerts,
    error,
    availableSymbols,
    isRefreshing,
    isRefreshEnabled: true,

    refresh,
    pauseScans: () => pauseScansMutation.mutate(),
    resumeScans: () => resumeScansMutation.mutate(),
    stopScans: () => stopScansMutation.mutate(),
    triggerScanNow: () => triggerScanMutation.mutate(),
    isPausingScans: pauseScansMutation.isPending,
    isResumingScans: resumeScansMutation.isPending,
    isStoppingScans: stopScansMutation.isPending,
    isTriggeringScan: triggerScanMutation.isPending,
    stopRequested: Boolean((scanControl as Record<string, unknown> | null)?.stop_requested),
  }
}
