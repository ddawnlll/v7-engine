import { useQuery } from '@tanstack/react-query'

import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { fetchOperateCandidates, fetchReviewEngineBehavior } from '../lib/api'
import { formatNumber } from '../lib/format'

export function ReviewEnginePerformanceRoute() {
  const behaviorQuery = useQuery({ queryKey: ['review-engine-performance'], queryFn: () => fetchReviewEngineBehavior(), refetchInterval: 30_000, refetchOnWindowFocus: false })
  const candidatesQuery = useQuery({ queryKey: ['operate-candidates', 'review-performance'], queryFn: fetchOperateCandidates, refetchOnWindowFocus: false })

  const evaluation = behaviorQuery.data?.evaluation?.expectancy
  const regimes = behaviorQuery.data?.evaluation?.regimes?.rows ?? []
  const candidates = candidatesQuery.data?.items ?? []
  const comparisons = candidatesQuery.data?.comparisons ?? []
  const championArtifactVersion = comparisons[0]?.comparison_to_champion?.champion_model_artifact_version ?? null

  if (behaviorQuery.isLoading && !behaviorQuery.data) {
    return <AnimatedRoute><EmptyState message="Loading engine performance review..." /></AnimatedRoute>
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Review · Engine Performance</p>
          <h1 className="text-3xl font-semibold tracking-[-0.05em] text-stone-950">Expectancy, win rate, regime breakdown, and model comparison.</h1>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          <MetricCard label="Win rate" value={evaluation?.win_rate == null ? '--' : `${formatNumber(Number(evaluation.win_rate) * 100, 1)}%`} />
          <MetricCard label="Expectancy" value={evaluation?.expectancy_r == null ? '--' : formatNumber(Number(evaluation.expectancy_r), 2)} />
          <MetricCard label="Resolved outcomes" value={formatNumber(evaluation?.resolved_outcome_count ?? 0, 0)} />
        </section>

        <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
          <h2 className="text-lg font-semibold text-stone-950">Regime breakdown</h2>
          {!regimes.length ? <div className="mt-4"><EmptyState message="No resolved regime rows yet." /></div> : (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="pb-2 pr-4">Regime</th>
                    <th className="pb-2 pr-4">Resolved</th>
                    <th className="pb-2 pr-4">Win rate</th>
                    <th className="pb-2 pr-4">Expectancy</th>
                    <th className="pb-2 pr-4">Fallback rate</th>
                    <th className="pb-2 pr-4">Block rate</th>
                  </tr>
                </thead>
                <tbody>
                  {regimes.map((row, index) => (
                    <tr key={`${String((row as { regime_label?: string }).regime_label ?? 'regime')}-${index}`} className="border-t border-stone-900/8">
                      <td className="py-3 pr-4">{String((row as { regime_label?: string }).regime_label ?? '--')}</td>
                      <td className="py-3 pr-4">{formatNumber((row as { resolved_count?: number }).resolved_count ?? 0, 0)}</td>
                      <td className="py-3 pr-4">{(row as { win_rate?: number }).win_rate == null ? '--' : `${formatNumber(Number((row as { win_rate?: number }).win_rate) * 100, 1)}%`}</td>
                      <td className="py-3 pr-4">{(row as { expectancy_r?: number }).expectancy_r == null ? '--' : formatNumber(Number((row as { expectancy_r?: number }).expectancy_r), 2)}</td>
                      <td className="py-3 pr-4">{(row as { fallback_rate?: number }).fallback_rate == null ? '--' : `${formatNumber(Number((row as { fallback_rate?: number }).fallback_rate) * 100, 1)}%`}</td>
                      <td className="py-3 pr-4">{(row as { block_rate?: number }).block_rate == null ? '--' : `${formatNumber(Number((row as { block_rate?: number }).block_rate) * 100, 1)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
          <h2 className="text-lg font-semibold text-stone-950">Cross-run model/version comparison</h2>
          {!comparisons.length && !candidates.length ? <div className="mt-4"><EmptyState message="No candidate models registered." /></div> : (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="pb-2 pr-4">Artifact</th>
                    <th className="pb-2 pr-4">Engine version</th>
                    <th className="pb-2 pr-4">Dataset</th>
                    <th className="pb-2 pr-4">Validated</th>
                  </tr>
                </thead>
                <tbody>
                  {(comparisons.length ? comparisons : candidates).map((row) => (
                    <tr key={String(row.model_artifact_version ?? 'candidate')} className="border-t border-stone-900/8">
                      <td className="py-3 pr-4">
                        <div className="font-semibold text-stone-950">{String(row.model_artifact_version ?? '--')}</div>
                        {championArtifactVersion ? <div className="text-xs text-stone-500">Champion: {String(championArtifactVersion)}</div> : null}
                      </td>
                      <td className="py-3 pr-4">{String(row.engine_version ?? '--')}</td>
                      <td className="py-3 pr-4">{String(row.dataset_version ?? '--')}</td>
                      <td className="py-3 pr-4">{row.validation_passed ? 'Yes' : 'No'}</td>
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
