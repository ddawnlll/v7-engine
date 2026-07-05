import { useEffect } from 'react'

import { useMutation, useQuery } from '@tanstack/react-query'
import { AnimatePresence } from 'framer-motion'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Toaster } from 'sonner'

import { Navbar } from './components/navigation/Navbar'
import { WorkspaceShell } from './components/navigation/WorkspaceShell'
import { useSettings } from './contexts/SettingsContext'
import { useProfileScopeOptions } from './hooks/useProfileScopeOptions'
import { fetchEngineHealthForScope, fetchJobsForScope, fetchOperatorAlertsForScope, fetchPortfolioForScope, fetchRuntimeProfileReadOnlyExposure, fetchRuntimeSettingsForScope, fetchSymbols, getCircuitBreakerState, pauseScans, resumeScans, stopScans, triggerScanNow } from './lib/api'
import { statusTone } from './lib/format'
import { DEFAULT_PROFILE_SCOPE } from './lib/profileScope'
import { queryClient } from './lib/queryClient'
import { legacyRouteRedirects, workspaceByKey } from './lib/workspaces'
import { AdminRoute } from './routes/AdminRoute'
import { AlertsRoute } from './routes/AlertsRoute'
import { DashboardRoute } from './routes/DashboardRoute'
import { TradeOverviewRoute } from './routes/TradeOverviewRoute'
import { EngineBehaviorRoute } from './routes/EngineBehaviorRoute'
import { EnginePerformanceRoute } from './routes/EnginePerformanceRoute'
import { FailureAnalyticsRoute } from './routes/FailureAnalyticsRoute'
import { LoggingRoute } from './routes/LoggingRoute'
import { MarketsRoute } from './routes/MarketsRoute'
import { OperateControlRoute } from './routes/OperateControlRoute'
import { PortfolioRoute } from './routes/PortfolioRoute'
import { RuntimeConfigRoute } from './routes/RuntimeConfigRoute'
import { ScansRoute } from './routes/ScansRoute'
import { SettingsRoute } from './routes/SettingsRoute'
import { SelfLearningRoute } from './routes/SelfLearningRoute'
import { ReviewLearningPage } from './routes/ReviewLearningPage'
import { SimulationsRoute } from './routes/SimulationsRoute'
import { StorageRoute } from './routes/StorageRoute'
import { TradesRoute } from './routes/TradesRoute'
import { ManualOrderRoute } from './routes/ManualOrderRoute'
import type { AlertItem, CircuitBreakerState, OperatorAlertRow } from './lib/types'

function toneToBadgeTone(tone: string): 'neutral' | 'good' | 'warn' | 'bad' {
  if (tone === 'tone-good') return 'good'
  if (tone === 'tone-warn') return 'warn'
  if (tone === 'tone-bad') return 'bad'
  return 'neutral'
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

function LegacyRedirect({ to }: { to: string }) {
  const location = useLocation()
  return <Navigate replace to={`${to}${location.search}${location.hash}`} />
}

function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const { settings, settingsSignature, updateSettings } = useSettings()
  const { options: profileOptions } = useProfileScopeOptions()
  const routeProfileScope = new URLSearchParams(location.search).get('profile') || settings.preferredProfileScope
  const isSyntheticSimulationScope = String(routeProfileScope).startsWith('simulation-')
  const activeProfileScope = isSyntheticSimulationScope ? DEFAULT_PROFILE_SCOPE : routeProfileScope

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
  const health = healthQuery.data ?? null
  const jobs = jobsQuery.data ?? null
  const portfolio = portfolioQuery.data ?? null
  const runtimeSettings = settingsQuery.data ?? {}
  const engineLabel = String(health?.status ?? 'unknown')
  const engineTone = toneToBadgeTone(statusTone(engineLabel))
  const criticalAlert = (health?.alert_summary?.items ?? []).find((item) => String(item?.severity ?? '').toLowerCase() === 'critical')
  const engineStatusDetail = (() => {
    if (engineLabel.toLowerCase() !== 'degraded') return { detail: null, href: null }
    if (health?.db_connected === false) return { detail: 'database disconnected', href: '/operate/control' }
    if (String(health?.degraded_reason ?? '').toLowerCase() === 'last_error') {
      const message = String((health?.last_error as { message?: string | null } | null)?.message ?? '').trim()
      return { detail: message || 'recent runtime error', href: '/operate/logs' }
    }
    if (Number(health?.alert_summary?.critical ?? 0) > 0) {
      return { detail: String(criticalAlert?.message ?? criticalAlert?.kind ?? 'critical alert active'), href: '/operate/alerts' }
    }
    const h = health as Record<string, unknown>
    if (Number(h?.heartbeat_age_seconds ?? 0) > 180 || String(h?.degraded_reason ?? '') === 'runner_heartbeat_stale') {
      return { detail: `runner heartbeat stale (${Math.round(Number(h?.heartbeat_age_seconds ?? 0))}s)`, href: '/operate/control' }
    }
    if (String(health?.stream?.status ?? '').toUpperCase() === 'DEGRADED') {
      return {
        detail: String((health?.stream as { error_text?: string | null } | null)?.error_text ?? 'user data stream degraded'),
        href: '/operate/control',
      }
    }
    if (Boolean((health?.stream as { reconnect_required?: boolean } | null)?.reconnect_required)) {
      return { detail: 'user data stream reconnect required', href: '/operate/control' }
    }
    if (String(health?.reconciliation?.status ?? '').toUpperCase() === 'DEGRADED') {
      return {
        detail: String((health?.reconciliation as { message?: string | null } | null)?.message ?? 'reconciliation degraded'),
        href: '/operate/control',
      }
    }
    if (String((health?.profile as { connectivity?: { status?: string | null } } | null)?.connectivity?.status ?? '').toLowerCase() === 'error') {
      return { detail: 'profile connectivity error', href: '/operate/config' }
    }
    if (String((health?.profile as { connectivity?: { status?: string | null } } | null)?.connectivity?.status ?? '').toLowerCase() === 'missing_credentials') {
      return { detail: 'profile credentials missing', href: '/operate/config' }
    }
    return { detail: 'recent runtime error or profile alert', href: '/operate/logs' }
  })()
  const engineDetail = engineStatusDetail.detail
  const engineDetailHref = engineStatusDetail.href
  const queuePending = Number(jobs?.pending ?? 0)
  const queueFailed = Number(jobs?.failed ?? 0)
  const netR = Number(portfolio?.summary?.net_r ?? 0)
  const expectedNetR = Number(portfolio?.summary?.expected_net_r ?? netR)
  const circuitBreaker = (circuitBreakerQuery.data?.state ?? {}) as CircuitBreakerState
  const scanControl = health?.scan_control ?? null
  const isScanPaused = String(scanControl?.desired_state ?? '').toUpperCase() === 'PAUSED'
  const hasActiveScan = String(scanControl?.active_status ?? '').toUpperCase() === 'RUNNING' || Boolean(scanControl?.active_run_id)
  const alerts = (alertsQuery.data?.items ?? []).map(mapAlertRow)
  const error = [healthQuery.error, jobsQuery.error, alertsQuery.error, portfolioQuery.error, settingsQuery.error, circuitBreakerQuery.error]
    .find((item) => item instanceof Error)
  const availableSymbols = preferLargerSymbolUniverse(symbolsQuery.data?.symbols, splitCsv(runtimeSettings.AUTONOMOUS_SYMBOLS))
  const isRefreshing = healthQuery.isFetching || jobsQuery.isFetching || alertsQuery.isFetching || portfolioQuery.isFetching || settingsQuery.isFetching || symbolsQuery.isFetching || circuitBreakerQuery.isFetching

  useEffect(() => {
    if (new URLSearchParams(location.search).get('profile')) {
      return
    }
    if (!settings.preferredProfileScope || settings.preferredProfileScope === 'paper-main') {
      return
    }
    const nextParams = new URLSearchParams(location.search)
    nextParams.set('profile', settings.preferredProfileScope)
    navigate({ pathname: location.pathname, search: `?${nextParams.toString()}` }, { replace: true })
  }, [location.pathname, location.search, navigate, settings.preferredProfileScope])

  return (
    <div className={`min-h-screen antialiased transition-colors ${
      settings.theme === 'dark'
        ? 'bg-[radial-gradient(circle_at_top_left,rgba(34,197,94,0.08),transparent_22%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.10),transparent_28%),linear-gradient(180deg,#0b1220,#111827)] text-slate-100'
        : 'bg-[radial-gradient(circle_at_top_left,rgba(222,214,199,0.72),transparent_22%),radial-gradient(circle_at_bottom_right,rgba(95,143,138,0.16),transparent_28%),linear-gradient(180deg,#f7f3ea,#ece5d6)] text-stone-900'
    }`}>
      <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-5 px-3 py-3 sm:px-5 sm:py-5 lg:px-6">
        <Navbar
          engineLabel={engineLabel}
          engineTone={engineTone}
          engineDetail={engineDetail}
          engineDetailHref={engineDetailHref}
          analyzerEngineName={health?.analyzer?.active_engine}
          analyzerEngineVersion={health?.analyzer?.active_engine_version}
          analyzerFallbackCount={health?.analyzer?.fallback_count}
          analyzerLastFallbackReason={health?.analyzer?.last_fallback_reason}
          selfLearningModelVersion={health?.self_learning?.active_model_version}
          generatedAt={health?.uptime_seconds != null ? new Date(Date.now() - health.uptime_seconds * 1000).toISOString() : undefined}
          nextAutoScanAt={health?.next_scan_at_utc}
          circuitBreakerStatus={String(circuitBreaker.status ?? 'CLOSED')}
          circuitBreakerReason={String(circuitBreaker.reason ?? '')}
          circuitBreakerAutoResumeAt={circuitBreaker.auto_resume_at ?? undefined}
          queuePending={queuePending}
          queueFailed={queueFailed}
          netR={netR}
          expectedNetR={expectedNetR}
          alerts={alerts}
          availableSymbols={availableSymbols}
          profileOptions={profileOptions}
          activeProfileScope={activeProfileScope}
          onProfileScopeChange={(nextValue) => {
            updateSettings({ preferredProfileScope: nextValue })
            const nextParams = new URLSearchParams(location.search)
            if (nextValue === 'paper-main') {
              nextParams.delete('profile')
            } else {
              nextParams.set('profile', nextValue)
            }
            navigate({ pathname: location.pathname, search: nextParams.toString() ? `?${nextParams.toString()}` : '' })
          }}
          onRefresh={() => {
            void healthQuery.refetch()
            void jobsQuery.refetch()
            void alertsQuery.refetch()
            void portfolioQuery.refetch()
            void settingsQuery.refetch()
            void symbolsQuery.refetch()
            void circuitBreakerQuery.refetch()
          }}
          onPauseScans={() => pauseScansMutation.mutate()}
          onResumeScans={() => resumeScansMutation.mutate()}
          onStopScans={() => stopScansMutation.mutate()}
          onTriggerScanNow={() => triggerScanMutation.mutate()}
          isScanPaused={isScanPaused}
          hasActiveScan={hasActiveScan}
          stopRequested={Boolean(scanControl?.stop_requested)}
          isPausingScans={pauseScansMutation.isPending}
          isResumingScans={resumeScansMutation.isPending}
          isStoppingScans={stopScansMutation.isPending}
          isRefreshing={isRefreshing}
          isTriggeringScan={triggerScanMutation.isPending}
        />

        {error instanceof Error ? (
          <div className="rounded-[1.5rem] border border-rose-700/12 bg-rose-50/78 px-5 py-4 text-sm text-rose-800 shadow-[0_14px_32px_rgba(157,60,60,0.08)]">
            {error.message}
          </div>
        ) : null}

        <main className="pb-6" key={settingsSignature}>
          <AnimatePresence mode="wait">
            <Routes location={location} key={location.pathname}>
              <Route path="/" element={<Navigate to="/trade/overview" replace />} />

              <Route
                path="/trade"
                element={
                  <WorkspaceShell
                    label={workspaceByKey.trade.label}
                    description={workspaceByKey.trade.description}
                    icon={workspaceByKey.trade.icon}
                    tabs={workspaceByKey.trade.tabs}
                  />
                }
              >
                <Route index element={<Navigate to="overview" replace />} />
                <Route path="overview" element={<TradeOverviewRoute />} />
                <Route path="markets" element={<MarketsRoute />} />
                <Route path="scans" element={<ScansRoute />} />
                <Route path="trades" element={<TradesRoute />} />
                <Route path="portfolio" element={<PortfolioRoute />} />
                <Route path="manual-order" element={<ManualOrderRoute />} />
              </Route>

              <Route
                path="/review"
                element={
                  <WorkspaceShell
                    label={workspaceByKey.review.label}
                    description={workspaceByKey.review.description}
                    icon={workspaceByKey.review.icon}
                    tabs={workspaceByKey.review.tabs}
                  />
                }
              >
                <Route index element={<Navigate to="engine/performance" replace />} />
                <Route path="engine">
                  <Route index element={<Navigate to="performance" replace />} />
                  <Route path="performance" element={<EnginePerformanceRoute />} />
                  <Route path="behavior" element={<EngineBehaviorRoute />} />
                </Route>
                <Route path="failures" element={<FailureAnalyticsRoute />} />
                <Route path="learning" element={<ReviewLearningPage />} />
              </Route>

              <Route
                path="/operate"
                element={
                  <WorkspaceShell
                    label={workspaceByKey.operate.label}
                    description={workspaceByKey.operate.description}
                    icon={workspaceByKey.operate.icon}
                    tabs={workspaceByKey.operate.tabs}
                  />
                }
              >
                <Route index element={<Navigate to="control" replace />} />
                <Route path="control" element={<OperateControlRoute />} />
                <Route path="alerts" element={<AlertsRoute />} />
                <Route path="logs" element={<LoggingRoute />} />
                <Route path="config" element={<RuntimeConfigRoute />} />
              </Route>

              <Route
                path="/system"
                element={
                  <WorkspaceShell
                    label={workspaceByKey.system.label}
                    description={workspaceByKey.system.description}
                    icon={workspaceByKey.system.icon}
                    tabs={workspaceByKey.system.tabs}
                  />
                }
              >
                <Route index element={<Navigate to="preferences" replace />} />
                <Route path="preferences" element={<SettingsRoute />} />
                <Route path="storage" element={<StorageRoute />} />
                <Route path="simulations" element={<SimulationsRoute />} />
              </Route>

              <Route path="/operations/admin" element={<AdminRoute />} />

              {Object.entries(legacyRouteRedirects).map(([from, to]) => (
                <Route key={from} path={from} element={<LegacyRedirect to={to} />} />
              ))}
            </Routes>
          </AnimatePresence>
        </main>

        <Toaster
          position="bottom-right"
          richColors
          expand
          toastOptions={{
            classNames: {
              toast: 'rounded-[1.3rem] border border-stone-900/8 bg-white/92 text-stone-900 shadow-[0_24px_60px_rgba(61,49,31,0.18)] backdrop-blur-xl',
              title: 'text-sm font-semibold text-stone-950',
              description: 'text-sm text-stone-600',
              actionButton: 'bg-stone-950 text-stone-50',
              cancelButton: 'bg-stone-950/[0.05] text-stone-700',
            },
          }}
        />
      </div>
    </div>
  )
}

export default App
