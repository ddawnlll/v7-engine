import { useEffect } from 'react'

import { AnimatePresence } from 'framer-motion'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Toaster } from 'sonner'

import { Navbar } from './components/navigation/Navbar'
import { WorkspaceShell } from './components/navigation/WorkspaceShell'
import { useSettings } from './contexts/SettingsContext'
import { useProfileScopeOptions } from './hooks/useProfileScopeOptions'
import { useShellStatusQuery } from './hooks/useShellStatusQuery'
import { DEFAULT_PROFILE_SCOPE } from './lib/profileScope'
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

  const shell = useShellStatusQuery(activeProfileScope)

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
          engineLabel={shell.engineLabel}
          engineTone={shell.engineTone}
          engineDetail={shell.engineDetail}
          engineDetailHref={shell.engineDetailHref}
          analyzerEngineName={shell.health?.analyzer?.active_engine as string | undefined}
          analyzerEngineVersion={shell.health?.analyzer?.active_engine_version as string | undefined}
          analyzerFallbackCount={shell.health?.analyzer?.fallback_count as number | undefined}
          analyzerLastFallbackReason={shell.health?.analyzer?.last_fallback_reason as string | null | undefined}
          selfLearningModelVersion={(shell.health?.self_learning as Record<string, unknown> | undefined)?.active_model_version as string | null | undefined}
          generatedAt={shell.health?.uptime_seconds != null ? new Date(Date.now() - (shell.health.uptime_seconds as number) * 1000).toISOString() : undefined}
          nextAutoScanAt={shell.health?.next_scan_at_utc as string | undefined}
          circuitBreakerStatus={String(shell.circuitBreaker.status ?? 'CLOSED')}
          circuitBreakerReason={String(shell.circuitBreaker.reason ?? '')}
          circuitBreakerAutoResumeAt={shell.circuitBreaker.auto_resume_at ?? undefined}
          queuePending={shell.queuePending}
          queueFailed={shell.queueFailed}
          netR={shell.netR}
          expectedNetR={shell.expectedNetR}
          alerts={shell.alerts}
          availableSymbols={shell.availableSymbols}
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
          onRefresh={shell.refresh}
          onPauseScans={shell.pauseScans}
          onResumeScans={shell.resumeScans}
          onStopScans={shell.stopScans}
          onTriggerScanNow={shell.triggerScanNow}
          isScanPaused={shell.isScanPaused}
          hasActiveScan={shell.hasActiveScan}
          stopRequested={shell.stopRequested}
          isPausingScans={shell.isPausingScans}
          isResumingScans={shell.isResumingScans}
          isStoppingScans={shell.isStoppingScans}
          isRefreshing={shell.isRefreshing}
          isTriggeringScan={shell.isTriggeringScan}
        />

        {shell.error instanceof Error ? (
          <div className="rounded-[1.5rem] border border-rose-700/12 bg-rose-50/78 px-5 py-4 text-sm text-rose-800 shadow-[0_14px_32px_rgba(157,60,60,0.08)]">
            {shell.error.message}
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
