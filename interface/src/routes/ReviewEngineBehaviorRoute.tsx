import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'

import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { fetchReviewDecisionEvent, fetchReviewDecisionEvents, fetchReviewEngineBehavior, fetchReviewShadowComparison } from '../lib/api'
import { formatNumber } from '../lib/format'

export function ReviewEngineBehaviorRoute() {
  const [searchParams] = useSearchParams()
  const selectedEventId = searchParams.get('event_id') ?? ''
  const behaviorQuery = useQuery({ queryKey: ['review-engine-behavior'], queryFn: () => fetchReviewEngineBehavior(), refetchInterval: 30_000, refetchOnWindowFocus: false })
  const shadowQuery = useQuery({ queryKey: ['review-shadow-comparison'], queryFn: () => fetchReviewShadowComparison(), refetchInterval: 30_000, refetchOnWindowFocus: false })
  const eventsQuery = useQuery({ queryKey: ['review-decision-events'], queryFn: () => fetchReviewDecisionEvents({ limit: 50 }), refetchInterval: 30_000, refetchOnWindowFocus: false })
  const detailQuery = useQuery({ queryKey: ['review-decision-event', selectedEventId], queryFn: () => fetchReviewDecisionEvent(selectedEventId), enabled: Boolean(selectedEventId), refetchOnWindowFocus: false })

  const behavior = behaviorQuery.data
  const shadow = shadowQuery.data
  const events = eventsQuery.data?.items ?? []

  if (behaviorQuery.isLoading && !behavior) {
    return <AnimatedRoute><EmptyState message="Loading engine behavior review..." /></AnimatedRoute>
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Review · Engine Behavior</p>
          <h1 className="text-3xl font-semibold tracking-[-0.05em] text-stone-950">Fallbacks, blocks, divergence, and decision evidence.</h1>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Fallback rate" value={`${formatNumber((behavior?.fallback_rate ?? 0) * 100, 1)}%`} />
          <MetricCard label="Timeout rate" value={`${formatNumber((behavior?.timeout_rate ?? 0) * 100, 1)}%`} />
          <MetricCard label="Block rate" value={`${formatNumber((behavior?.block_rate ?? 0) * 100, 1)}%`} />
          <MetricCard label="Shadow divergence" value={`${formatNumber((shadow?.divergence_rate ?? 0) * 100, 1)}%`} />
        </section>

        {selectedEventId ? (
          <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-stone-950">Decision event detail</h2>
              <Link className="text-sm font-semibold text-teal-800" to="/review/engine/behavior">Clear</Link>
            </div>
            {!detailQuery.data ? (
              <div className="mt-4"><EmptyState message="Loading decision event detail..." /></div>
            ) : (
              <div className="mt-4 grid gap-2 text-sm text-stone-700">
                <div>Event: <span className="font-semibold text-stone-950">{String(detailQuery.data.identity?.decision_event_id ?? '--')}</span></div>
                <div>Engine: <span className="font-semibold text-stone-950">{String(detailQuery.data.lineage?.engine_name ?? '--')} {String(detailQuery.data.lineage?.engine_version ?? '')}</span></div>
                <div>Symbol: <span className="font-semibold text-stone-950">{String(detailQuery.data.scope?.symbol ?? '--')} {String(detailQuery.data.scope?.interval ?? '')}</span></div>
                <div>Status: <span className="font-semibold text-stone-950">{String(detailQuery.data.decision_summary?.signal_status ?? '--')}</span></div>
                <div>Action: <span className="font-semibold text-stone-950">{String(detailQuery.data.decision_summary?.recommended_action ?? '--')} {String(detailQuery.data.decision_summary?.direction ?? '')}</span></div>
                <div>Fallback used: <span className="font-semibold text-stone-950">{detailQuery.data.runtime_interpretation?.fallback_used ? 'Yes' : 'No'}</span></div>
                <div>Deterministic alignment: <span className="font-semibold text-stone-950">{String(detailQuery.data.runtime_interpretation?.deterministic_alignment ?? '--')}</span></div>
              </div>
            )}
          </section>
        ) : null}

        <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-stone-950">Decision events</h2>
            <div className="text-sm text-stone-500">{formatNumber(eventsQuery.data?.count ?? events.length, 0)} visible</div>
          </div>
          {!events.length ? (
            <div className="mt-4"><EmptyState message="No decision events yet. Sparse shadow data is expected early in rollout." /></div>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="pb-2 pr-4">Event</th>
                    <th className="pb-2 pr-4">Symbol</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 pr-4">Fallback</th>
                    <th className="pb-2 pr-4">Deterministic</th>
                    <th className="pb-2 pr-4">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((item) => (
                    <tr key={String(item.identity?.decision_event_id ?? 'event')} className="border-t border-stone-900/8">
                      <td className="py-3 pr-4"><Link className="font-semibold text-teal-800" to={`/review/engine/behavior?event_id=${encodeURIComponent(String(item.identity?.decision_event_id ?? ''))}`}>{String(item.identity?.decision_event_id ?? '--')}</Link></td>
                      <td className="py-3 pr-4">{String(item.scope?.symbol ?? '--')}</td>
                      <td className="py-3 pr-4">{String(item.decision_summary?.signal_status ?? '--')}</td>
                      <td className="py-3 pr-4">{item.runtime_interpretation?.fallback_used ? 'Yes' : 'No'}</td>
                      <td className="py-3 pr-4">{String(item.runtime_interpretation?.deterministic_alignment ?? '--')}</td>
                      <td className="py-3 pr-4">{String(item.decision_summary?.recommended_action ?? '--')} {String(item.decision_summary?.direction ?? '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </AnimatedRoute>
  )
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
      <div className="text-sm text-stone-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-stone-950">{value}</div>
    </div>
  )
}
