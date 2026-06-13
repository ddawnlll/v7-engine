import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { fetchReviewLearning, fetchRuntimeMetrics } from '../lib/api'
import { formatNumber } from '../lib/format'

export function ReviewLearningPage() {
  const learningQuery = useQuery({ queryKey: ['review-learning'], queryFn: fetchReviewLearning, refetchOnWindowFocus: false })
  const metricsQuery = useQuery({ queryKey: ['runtime-metrics', 'review-learning'], queryFn: fetchRuntimeMetrics, refetchOnWindowFocus: false })

  const payload = learningQuery.data
  const runs = payload?.training_runs ?? []
  const datasets = payload?.dataset_versions ?? []
  const folds = payload?.walk_forward_fold_results ?? []
  const holdouts = payload?.holdout_summaries ?? []
  const drifts = payload?.calibration_drift ?? []
  const comparisons = payload?.candidate_comparisons ?? []
  const route = payload?.prepare_promotion_evidence_route ?? '/operate/control'

  if (learningQuery.isLoading && !payload) {
    return <AnimatedRoute><EmptyState message="Loading learning review..." /></AnimatedRoute>
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Review · Learning</p>
          <h1 className="text-3xl font-semibold tracking-[-0.05em] text-stone-950">Training runs, datasets, validation artifacts, and challenger evidence.</h1>
          <p className="mt-2 text-sm text-stone-600">Promotion actions remain in Operate Control. This page is review-only.</p>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <MetricCard label="Training runs" value={formatNumber(runs.length, 0)} />
          <MetricCard label="Dataset versions" value={formatNumber(datasets.length, 0)} />
          <MetricCard label="Resolved outcomes" value={formatNumber(metricsQuery.data?.resolved_outcome_count ?? 0, 0)} />
          <MetricCard label="Fallback rate" value={`${formatNumber((metricsQuery.data?.fallback_rate_24h ?? 0) * 100, 1)}%`} />
          <MetricCard label="Champion" value={String(metricsQuery.data?.champion_model_artifact_version ?? '--')} />
        </section>
        <section className="grid gap-4 md:grid-cols-2">
          <MetricCard label="Timeout rate" value={`${formatNumber((metricsQuery.data?.timeout_rate_24h ?? 0) * 100, 1)}%`} />
          <MetricCard label="Hard block rate" value={`${formatNumber((metricsQuery.data?.hard_block_rate_24h ?? 0) * 100, 1)}%`} />
        </section>

        <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-stone-950">Candidate comparison</h2>
            <Link className="text-sm font-semibold text-teal-800" to={route}>Prepare promotion evidence</Link>
          </div>
          {!comparisons.length ? <div className="mt-4"><EmptyState message="No candidate validation artifacts yet. Sparse learning history is expected early in rollout." /></div> : (
            <div className="mt-4 overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-stone-500">
                  <tr>
                    <th className="pb-2 pr-4">Artifact</th>
                    <th className="pb-2 pr-4">Role</th>
                    <th className="pb-2 pr-4">Validated</th>
                    <th className="pb-2 pr-4">Holdout</th>
                    <th className="pb-2 pr-4">Calibration drift</th>
                  </tr>
                </thead>
                <tbody>
                  {comparisons.map((row, index) => (
                    <tr key={`${String(row.model_artifact_version ?? 'candidate')}-${index}`} className="border-t border-stone-900/8">
                      <td className="py-3 pr-4 font-semibold text-stone-950">{String(row.model_artifact_version ?? '--')}</td>
                      <td className="py-3 pr-4">{String(row.role ?? '--')}</td>
                      <td className="py-3 pr-4">{row.validation_passed ? 'Yes' : 'No'}</td>
                      <td className="py-3 pr-4">{JSON.stringify(row.holdout_summary ?? {})}</td>
                      <td className="py-3 pr-4">{JSON.stringify(row.calibration_drift ?? {})}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="grid gap-4 xl:grid-cols-2">
          <DataPanel title="Training runs" items={runs} empty="No training runs recorded yet." />
          <DataPanel title="Dataset versions" items={datasets} empty="No dataset versions recorded yet." />
          <DataPanel title="Walk-forward fold results" items={folds} empty="No walk-forward folds available yet." />
          <DataPanel title="Holdout summaries" items={holdouts} empty="No holdout summaries available yet." />
          <DataPanel title="Calibration drift" items={drifts} empty="No calibration drift artifacts available yet." />
        </div>
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

function DataPanel({ title, items, empty }: { title: string; items: unknown[]; empty: string }) {
  return (
    <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
      <h2 className="text-lg font-semibold text-stone-950">{title}</h2>
      {!items.length ? <div className="mt-4"><EmptyState message={empty} /></div> : (
        <div className="mt-4 grid gap-2">
          {items.map((item, index) => (
            <pre key={`${title}-${index}`} className="overflow-x-auto rounded-[1rem] bg-stone-50/80 p-3 text-xs text-stone-700">{JSON.stringify(item, null, 2)}</pre>
          ))}
        </div>
      )}
    </section>
  )
}
