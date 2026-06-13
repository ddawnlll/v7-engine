import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Bell,
  Moon,
  Pause,
  Play,
  RefreshCw,
  Square,
  Sun,
  TimerReset,
  X,
} from 'lucide-react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'

import { formatTime } from '../../lib/format'
import { DEFAULT_PROFILE_SCOPE, withCurrentProfileScope } from '../../lib/profileScope'
import { useSettings } from '../../contexts/SettingsContext'
import type { AlertItem, ProfileScopeOption, ProfileScopeValue } from '../../lib/types'
import { workspaceDefinitions, workspaceShortcuts } from '../../lib/workspaces'

/* ---------------- NAV ITEMS ---------------- */

const primaryItems = workspaceDefinitions
const secondaryItems = workspaceShortcuts

function alertToneClasses(severity: AlertItem['severity']) {
  if (severity === 'critical') return 'bg-rose-50 text-rose-900 border-rose-900/10'
  if (severity === 'warning') return 'bg-amber-50 text-amber-900 border-amber-900/10'
  return 'bg-teal-50 text-teal-900 border-teal-900/10'
}

/* ---------------- COMPONENT ---------------- */

export function Navbar({
  engineLabel = 'Unavailable',
  engineTone = 'neutral',
  engineDetail,
  engineDetailHref,
  analyzerEngineName,
  analyzerEngineVersion,
  analyzerFallbackCount,
  analyzerLastFallbackReason,
  selfLearningModelVersion,
  generatedAt,
  nextAutoScanAt,
  circuitBreakerStatus = 'CLOSED',
  circuitBreakerReason,
  circuitBreakerAutoResumeAt,
  queuePending = 0,
  queueFailed = 0,
  netR = 0,
  expectedNetR = 0,
  alerts,
  availableSymbols,
  profileOptions = [],
  activeProfileScope = DEFAULT_PROFILE_SCOPE,
  onProfileScopeChange = () => {},
  onRefresh = () => {},
  onPauseScans = () => {},
  onResumeScans = () => {},
  onStopScans = () => {},
  onTriggerScanNow = () => {},
  isScanPaused = false,
  hasActiveScan = false,
  stopRequested = false,
  isPausingScans = false,
  isResumingScans = false,
  isStoppingScans = false,
  isRefreshing = false,
  isTriggeringScan = false,
}: {
  engineLabel?: string
  engineTone?: 'neutral' | 'good' | 'warn' | 'bad'
  engineDetail?: string | null
  engineDetailHref?: string | null
  analyzerEngineName?: string | null
  analyzerEngineVersion?: string | null
  analyzerFallbackCount?: number
  analyzerLastFallbackReason?: string | null
  selfLearningModelVersion?: string | null
  generatedAt?: string
  nextAutoScanAt?: string
  circuitBreakerStatus?: string
  circuitBreakerReason?: string
  circuitBreakerAutoResumeAt?: string
  queuePending?: number
  queueFailed?: number
  netR?: number
  expectedNetR?: number
  alerts: AlertItem[]
  availableSymbols: string[]
  profileOptions?: ProfileScopeOption[]
  activeProfileScope?: ProfileScopeValue
  onProfileScopeChange?: (nextValue: ProfileScopeValue) => void
  onRefresh?: () => void
  onPauseScans?: () => void
  onResumeScans?: () => void
  onStopScans?: () => void
  onTriggerScanNow?: () => void
  isScanPaused?: boolean
  hasActiveScan?: boolean
  stopRequested?: boolean
  isPausingScans?: boolean
  isResumingScans?: boolean
  isStoppingScans?: boolean
  isRefreshing?: boolean
  isTriggeringScan?: boolean
}) {
  const location = useLocation()
  const navigate = useNavigate()
  const { term, settings, updateSettings } = useSettings()

  const [alertsOpen, setAlertsOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [commandQuery, setCommandQuery] = useState('')
  const [nowMs, setNowMs] = useState(() => Date.now())

  const unreadCount = alerts.filter((a) => a.unread !== false).length
  const withScopedSearch = (to: string) => withCurrentProfileScope(to, location.search)

  const filteredSymbols = useMemo(() => {
    const term = commandQuery.trim().toUpperCase()
    if (!term) return availableSymbols.slice(0, 12)
    return availableSymbols.filter((s) => s.includes(term)).slice(0, 12)
  }, [availableSymbols, commandQuery])

  /* ---------------- HOTKEYS ---------------- */

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCommandOpen((v) => !v)
      }
      if (e.key === 'Escape') {
        setAlertsOpen(false)
        setCommandOpen(false)
        setMoreOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    setAlertsOpen(false)
    setCommandOpen(false)
    setMoreOpen(false)
  }, [location.pathname, location.search])

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const nextAutoScanLabel = useMemo(() => {
    if (String(circuitBreakerStatus).toUpperCase() === 'OPEN') return 'Blocked'
    if (!nextAutoScanAt) return '--'
    const nextMs = new Date(nextAutoScanAt).getTime()
    if (!Number.isFinite(nextMs)) return '--'
    const secondsRemaining = Math.max(0, Math.ceil((nextMs - nowMs) / 1000))
    return `${secondsRemaining}s`
  }, [circuitBreakerStatus, nextAutoScanAt, nowMs])

  const circuitToneClass = useMemo(() => {
    const status = String(circuitBreakerStatus).toUpperCase()
    if (status === 'OPEN') return 'bg-rose-50 text-rose-900 border-rose-900/10'
    if (status === 'DEGRADED') return 'bg-amber-50 text-amber-900 border-amber-900/10'
    return 'bg-teal-50 text-teal-900 border-teal-900/10'
  }, [circuitBreakerStatus])

  const circuitResumeLabel = useMemo(() => {
    if (!circuitBreakerAutoResumeAt) return null
    const resumeMs = new Date(circuitBreakerAutoResumeAt).getTime()
    if (!Number.isFinite(resumeMs)) return null
    const secondsRemaining = Math.max(0, Math.ceil((resumeMs - nowMs) / 1000))
    return `${secondsRemaining}s`
  }, [circuitBreakerAutoResumeAt, nowMs])

  /* ---------------- UI ---------------- */

  return (
    <>
      <header className="sticky top-3 z-20 rounded-[1.6rem] border border-stone-900/8 bg-white/80 px-4 py-3 shadow backdrop-blur-md">

        {/* -------- TOP ROW -------- */}
        <div className="flex items-center justify-between">

          {/* LEFT */}
          <div className="flex items-center gap-4">

            {/* LOGO */}
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-950 text-white">
                <Activity className="h-5 w-5" />
              </div>
              <span className="text-sm font-semibold text-stone-800">
                Trading Bot V4
              </span>
            </div>

            {/* NAV */}
            <nav className="flex items-center gap-2">
              {primaryItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={withScopedSearch(item.to)}
                  className={({ isActive }) =>
                    `inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-semibold ${
                      isActive
                        ? 'bg-stone-950 text-white'
                        : 'text-stone-600 hover:bg-stone-100'
                    }`
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}

              {/* MORE */}
              <div className="relative">
                <button
                  onClick={() => setMoreOpen((v) => !v)}
                  className="rounded-full px-3 py-2 text-sm font-semibold text-stone-600 hover:bg-stone-100"
                >
                  More
                </button>

                {moreOpen && (
                  <div className="absolute left-0 mt-2 w-56 rounded-xl border border-stone-900/8 bg-white p-2 shadow-lg">
                    <div className="px-3 py-2 text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-stone-500">
                      Workspace Shortcuts
                    </div>
                    {secondaryItems.map((item) => (
                      <Link
                        key={item.to}
                        to={withScopedSearch(item.to)}
                        className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold text-stone-600 hover:bg-stone-100"
                      >
                        <item.icon className="h-4 w-4" />
                        {item.label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </nav>
          </div>

          {/* RIGHT */}
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-3 py-2 text-sm font-semibold text-stone-700">
              <span className="text-stone-500">Profile</span>
              <select
                value={activeProfileScope}
                onChange={(event) => onProfileScopeChange(event.target.value)}
                className="bg-transparent text-stone-900 outline-none"
                aria-label="Select profile"
              >
                {profileOptions.filter((option) => option.enabled && option.kind === 'profile').map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={onPauseScans}
              disabled={isPausingScans || isScanPaused}
              className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 px-3 py-2 text-sm font-semibold text-stone-700 transition hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-60"
              title={isScanPaused ? 'Autonomous scans are already paused' : 'Pause autonomous scans after the current control cycle'}
            >
              <Pause className={`h-4 w-4 ${isPausingScans ? 'animate-pulse' : ''}`} />
              Pause
            </button>

            <button
              onClick={onResumeScans}
              disabled={isResumingScans || (!isScanPaused && !stopRequested)}
              className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 px-3 py-2 text-sm font-semibold text-stone-700 transition hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-60"
              title={isScanPaused || stopRequested ? 'Resume autonomous scans' : 'Autonomous scans are already running'}
            >
              <Play className={`h-4 w-4 ${isResumingScans ? 'animate-pulse' : ''}`} />
              Resume
            </button>

            <button
              onClick={onStopScans}
              disabled={isStoppingScans || !hasActiveScan}
              className="inline-flex items-center gap-2 rounded-full border border-rose-900/10 bg-rose-50/80 px-3 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
              title={hasActiveScan ? 'Request a graceful stop for the active scan' : 'No active scan is currently running'}
            >
              <Square className={`h-4 w-4 ${isStoppingScans ? 'animate-pulse' : ''}`} />
              Stop
            </button>

            <button
              onClick={onTriggerScanNow}
              disabled={isTriggeringScan}
              className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 px-3 py-2 text-sm font-semibold text-stone-700 transition hover:bg-stone-100 disabled:cursor-not-allowed disabled:opacity-60"
              title={
                String(circuitBreakerStatus).toUpperCase() === 'OPEN'
                  ? `Autonomous scans are blocked by the circuit breaker. ${circuitBreakerReason || ''}`.trim()
                  : 'Skip the scan timer and trigger the next autonomous scan now'
              }
            >
              <TimerReset className={`h-4 w-4 ${isTriggeringScan ? 'animate-spin' : ''}`} />
              Scan now
            </button>

            {/* ⌘K */}
            <button
              onClick={() => setCommandOpen(true)}
              className="rounded-full p-2 text-sm font-semibold hover:bg-stone-100"
            >
              ⌘K
            </button>

            {/* ALERTS */}
            <button
              onClick={() => setAlertsOpen((v) => !v)}
              className="relative rounded-full p-2 hover:bg-stone-100"
              aria-label={unreadCount ? `${unreadCount} critical alerts` : 'No active alerts'}
              title={unreadCount ? `${unreadCount} critical alerts` : 'No active alerts'}
            >
              <Bell className="h-4 w-4" />
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-rose-600" />
              )}
            </button>

            <button
              onClick={() => updateSettings({ theme: settings.theme === 'dark' ? 'light' : 'dark' })}
              className="rounded-full p-2 hover:bg-stone-100"
              aria-label={settings.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
              title={settings.theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {settings.theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* -------- STATUS BAR -------- */}
        <div className="mt-2 flex items-center justify-between border-t pt-2 text-xs text-stone-600">

          <div className="flex items-center gap-3">

            {/* ENGINE */}
            <span className="flex items-center gap-1" title={engineDetail || undefined}>
              <span className={`h-2 w-2 rounded-full ${
                engineTone === 'good'
                  ? 'bg-teal-600'
                  : engineTone === 'bad'
                  ? 'bg-rose-600'
                  : engineTone === 'warn'
                  ? 'bg-amber-600'
                  : 'bg-stone-400'
              }`} />
              {engineLabel}
              {engineDetail ? (
                engineDetailHref ? (
                  <Link
                    to={withScopedSearch(engineDetailHref)}
                    className="max-w-[280px] truncate text-stone-500 underline decoration-dotted underline-offset-2 hover:text-stone-700"
                  >
                    · {engineDetail}
                  </Link>
                ) : (
                  <span className="max-w-[280px] truncate text-stone-500">· {engineDetail}</span>
                )
              ) : null}
            </span>

            {selfLearningModelVersion ? (
              <>
                <span>|</span>
                <span>
                  Self-learning <b>{selfLearningModelVersion}</b>
                </span>
              </>
            ) : null}

            {analyzerEngineName ? (
              <>
                <span>|</span>
                <span title={analyzerLastFallbackReason || undefined}>
                  Analyzer <b>{analyzerEngineName}</b>
                  {analyzerEngineVersion ? ` ${analyzerEngineVersion}` : ''}
                  {Number(analyzerFallbackCount || 0) > 0 ? ` · fb ${analyzerFallbackCount}` : ''}
                </span>
              </>
            ) : null}

            <span>|</span>

            {/* QUEUE */}
            <span>
              {term('queue')} <b>{queuePending}</b> / {term('failed')}{' '}
              <b className={queueFailed ? 'text-rose-600' : ''}>
                {queueFailed}
              </b>
            </span>

            <span>|</span>

            <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-semibold ${circuitToneClass}`}>
              Circuit {String(circuitBreakerStatus || 'CLOSED').toUpperCase()}
              {String(circuitBreakerStatus).toUpperCase() === 'OPEN' && circuitResumeLabel ? ` · ${circuitResumeLabel}` : ''}
            </span>

            {String(circuitBreakerStatus).toUpperCase() !== 'CLOSED' ? (
              <>
                <span>|</span>
                <span className="max-w-[340px] truncate" title={circuitBreakerReason || undefined}>
                  {circuitBreakerReason || 'Autonomous scans are safety-limited.'}
                </span>
              </>
            ) : null}

            <span>|</span>

            {/* NET R */}
            <span>
              {term('net_r')}{' '}
              <b className={netR >= 0 ? 'text-teal-700' : 'text-rose-600'}>
                {netR.toFixed(
                  settings.numberPrecision === 'auto'
                    ? 2
                    : settings.numberPrecision
                )}
                R
              </b>
            </span>

            <span>
              Expected{' '}
              <b className={expectedNetR >= 0 ? 'text-teal-700' : 'text-rose-600'}>
                {expectedNetR.toFixed(
                  settings.numberPrecision === 'auto'
                    ? 2
                    : settings.numberPrecision
                )}
                R
              </b>
            </span>

            <span>|</span>

            {/* NEXT AUTO SCAN */}
            <span>
              Next auto scan <b>{nextAutoScanLabel}</b>
            </span>

            <span>|</span>

            {/* TIME */}
            <span>{formatTime(generatedAt)}</span>
          </div>

          {/* REFRESH */}
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="p-1 rounded hover:bg-stone-100"
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`}
            />
          </button>
        </div>

        {/* -------- ALERT PANEL -------- */}
        {alertsOpen && (
          <div className="mt-3 grid gap-2 border rounded-xl p-3 bg-white">
            {alerts.length ? (
              alerts.slice(0, 5).map((alert) => (
                <Link
                  key={alert.id}
                  to={withScopedSearch(alert.route)}
                  className={`rounded-lg border px-3 py-2 ${alertToneClasses(alert.severity)}`}
                >
                  <div className="flex justify-between">
                    <span className="font-semibold">{alert.title}</span>
                    <span className="text-xs opacity-70">
                      {formatTime(alert.timestamp)}
                    </span>
                  </div>
                  <p className="text-sm opacity-80">{alert.message}</p>
                </Link>
              ))
            ) : (
              <div className="text-sm text-stone-500">
                No active alerts.
              </div>
            )}
          </div>
        )}
      </header>

      {/* -------- COMMAND PALETTE -------- */}
      {commandOpen && (
        <div className="fixed inset-0 z-40 bg-black/30 p-4">
          <div className="mx-auto mt-[12vh] max-w-lg rounded-xl bg-white p-4 shadow-lg">

            <div className="flex justify-between">
              <span className="font-semibold">Jump to symbol</span>
              <button onClick={() => setCommandOpen(false)}>
                <X />
              </button>
            </div>

            <input
              autoFocus
              value={commandQuery}
              onChange={(e) => setCommandQuery(e.target.value)}
              placeholder="BTC, ETH..."
              className="mt-3 w-full border rounded px-3 py-2"
            />

            <div className="mt-3 max-h-64 overflow-y-auto">
              {filteredSymbols.map((symbol) => (
                <button
                  key={symbol}
                  onClick={() => {
                    navigate(withScopedSearch(`/trade/markets?symbol=${symbol}`))
                    setCommandOpen(false)
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-stone-100 rounded"
                >
                  {symbol}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
