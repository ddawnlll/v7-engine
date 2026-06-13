import { useQuery } from '@tanstack/react-query'
import { Bell, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'

import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { fetchOperatorAlerts } from '../lib/api'
import { formatTime } from '../lib/format'
import type { OperatorAlertRow } from '../lib/types'

function toneClasses(severity: string) {
  const normalized = severity.toLowerCase()
  if (normalized === 'critical') return 'border-rose-900/10 bg-rose-50/88 text-rose-900'
  if (normalized === 'warning') return 'border-amber-900/10 bg-amber-50/88 text-amber-900'
  return 'border-teal-900/10 bg-teal-50/88 text-teal-900'
}

function alertRoute(alert: OperatorAlertRow) {
  const scope = String(alert.scope ?? '').toLowerCase()
  if (scope === 'scan') return '/operate/control'
  if (scope === 'database') return '/system/storage'
  if (scope === 'exchange') return '/trade/markets'
  return '/operate/control'
}

function alertTitle(alert: OperatorAlertRow) {
  return String(alert.kind ?? 'operator_alert').replaceAll('_', ' ')
}

export function AlertsRoute() {
  const alertsQuery = useQuery({
    queryKey: ['operator-alerts', 'page'],
    queryFn: fetchOperatorAlerts,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const alerts = alertsQuery.data?.items ?? []

  if (alertsQuery.isLoading && !alerts.length) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading alerts…" />
      </AnimatedRoute>
    )
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-5">
        <section className="rounded-[1.8rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_22px_44px_rgba(77,62,40,0.08)]">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-teal-800">
              <Bell className="h-4 w-4" strokeWidth={1.8} />
              Alerts
            </div>
            <h1 className="text-2xl font-semibold tracking-[-0.05em] text-stone-950">Operator attention queue</h1>
            <p className="max-w-3xl text-sm leading-7 text-stone-600">
              Active runtime alerts from the Python backend. Exchange, scan freshness, and database failures show up here first.
            </p>
          </div>
        </section>

        <section className="grid gap-3">
          {alerts.length ? alerts.map((alert, index) => (
            <Link
              key={`${String(alert.alert_id ?? alert.kind ?? index)}-${String(alert.detected_at_utc ?? '')}`}
              to={alertRoute(alert)}
              className={`rounded-[1.5rem] border p-4 shadow-[0_12px_24px_rgba(71,53,29,0.04)] transition hover:-translate-y-0.5 ${toneClasses(String(alert.severity ?? 'info'))}`}
            >
              <div className="flex flex-col gap-3 lg:grid lg:grid-cols-[170px_1fr_auto] lg:items-start">
                <div className="font-mono text-xs uppercase tracking-[0.18em] opacity-70">
                  {formatTime(alert.detected_at_utc)}
                </div>
                <div className="grid gap-1">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <TriangleAlert className="h-4 w-4" strokeWidth={1.8} />
                    {alertTitle(alert)}
                  </div>
                  <p className="text-sm leading-7 opacity-85">{String(alert.message ?? '')}</p>
                </div>
                <div className="text-sm font-semibold opacity-80">
                  Open
                </div>
              </div>
            </Link>
          )) : <EmptyState message="No active alerts right now." />}
        </section>
      </div>
    </AnimatedRoute>
  )
}
