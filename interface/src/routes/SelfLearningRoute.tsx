import { useMemo } from 'react'

import { useQuery } from '@tanstack/react-query'
import { BrainCircuit, Download, History, Radar, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { exportSelfLearningCsv, getSelfLearningMemories, getSelfLearningProfile, getSelfLearningStatus } from '../lib/api'
import { downloadFile, exportFilename } from '../lib/export'
import { formatNumber, formatTime, toNumber } from '../lib/format'
import type { SelfLearningMemory, SelfLearningProfilePayload, SelfLearningStatusPayload } from '../lib/types'

export function SelfLearningRoute() {
  const statusQuery = useQuery({
    queryKey: ['self-learning-status'],
    queryFn: getSelfLearningStatus,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const profileQuery = useQuery({
    queryKey: ['self-learning-profile'],
    queryFn: () => getSelfLearningProfile(30),
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })
  const memoriesQuery = useQuery({
    queryKey: ['self-learning-memories'],
    queryFn: () => getSelfLearningMemories({ lookbackDays: 30, limit: 20 }),
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  })

  const status = (statusQuery.data ?? {}) as SelfLearningStatusPayload
  const profile = (profileQuery.data ?? {}) as SelfLearningProfilePayload
  const memories = ((memoriesQuery.data?.items ?? []) as SelfLearningMemory[]) ?? []
  const expectancy = profile.expectancy_profiles ?? []
  const topActions = profile.top_recommended_actions_by_regime ?? []
  const shadows = profile.recent_shadow_decisions ?? []
  const runtime = status.self_learning_runtime ?? {}
  const runtimeBackendHealth = runtime.backend_health ?? {}
  const trainingTrigger = runtime.training_trigger ?? {}
  const latestComparison = runtime.latest_comparison ?? {}

  const regimeRows = useMemo(
    () =>
      Object.entries(profile.regime_counts ?? {})
        .sort((left, right) => right[1] - left[1])
        .slice(0, 12),
    [profile.regime_counts],
  )

  if (statusQuery.isLoading && profileQuery.isLoading && memoriesQuery.isLoading) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading self-learning foundations..." />
      </AnimatedRoute>
    )
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <section className="flex flex-wrap items-start justify-between gap-4 rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="grid gap-1">
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-stone-950">
              <BrainCircuit className="h-4 w-4 text-teal-800" />
              Self-learning foundations
            </div>
            <p className="text-sm text-stone-500">Context snapshots, replay coverage, offline policy rows, advisory-only shadow actions, and local runtime foundations.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={async () => {
                try {
                  const csv = await exportSelfLearningCsv()
                  downloadFile(csv, exportFilename('self-learning', 'csv'), 'text/csv;charset=utf-8')
                  toast.success('Learning CSV downloaded.')
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : 'Failed to export learning CSV.')
                }
              }}
              className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
            >
              <Download className="h-4 w-4" strokeWidth={1.8} />
              Export CSV
            </button>
            <div className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-stone-50 px-3 py-1.5 text-xs font-semibold text-stone-700">
              <RefreshCw className="h-3.5 w-3.5" />
              {formatTime(status.status?.generated_at ?? profile.generated_at)}
            </div>
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {[
            ['Memory records', formatNumber(status.status?.memory_count, 0)],
            ['Replay rows', formatNumber(status.status?.replay_count, 0)],
            ['Policy examples', formatNumber(status.status?.policy_example_count, 0)],
            ['Expectancy profiles', formatNumber(status.status?.expectancy_profile_count, 0)],
            ['Shadow decisions', formatNumber(status.status?.shadow_decision_count, 0)],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
              <p className="text-xs text-stone-500">{label}</p>
              <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-950">{value}</p>
            </div>
          ))}
        </section>

        <section className="rounded-[1.25rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
          <div className="flex items-center gap-2 text-sm font-semibold text-stone-950">
            <BrainCircuit className="h-4 w-4 text-teal-800" />
            Self-learning runtime
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-6">
            {[
              ['Readiness', String(runtime.current_readiness_state ?? 'FOUNDATION_ONLY')],
              ['Active model', String(runtime.active_model_version ?? '--')],
              ['Candidate model', String(runtime.candidate_model_version ?? '--')],
              ['Dataset rows', formatNumber(runtime.training_dataset_size, 0)],
              ['External memories', formatNumber(runtime.memory?.memory_row_count, 0)],
              ['Lance/ML backends', `${Object.values(runtimeBackendHealth).filter(Boolean).length}/${Object.keys(runtimeBackendHealth).length}`],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-[1rem] bg-stone-50/80 px-4 py-3">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">{label}</p>
                <p className="mt-2 text-sm font-semibold text-stone-950 break-all">{value}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[
            ['Train now', String(trainingTrigger.should_train ? 'YES' : 'NO')],
            ['Trigger reasons', String((trainingTrigger.reasons ?? []).join(', ') || '--')],
            ['Comparison status', String(latestComparison.status ?? '--')],
            ['Recommendation', String(latestComparison.recommendation ?? '--')],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-[1.2rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
              <p className="text-xs text-stone-500">{label}</p>
              <p className="mt-2 text-sm font-semibold text-stone-950 break-all">{value}</p>
            </div>
          ))}
        </section>

        <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <section className="rounded-[1.25rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <div className="flex items-center gap-2 text-sm font-semibold text-stone-950">
              <History className="h-4 w-4 text-teal-800" />
              Recent trade memories
            </div>
            <div className="mt-4 grid gap-3">
              {memories.length ? memories.map((memory) => (
                <div key={String(memory.signal_id ?? memory.id)} className="rounded-[1rem] border border-stone-900/8 bg-stone-50/80 px-4 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-stone-950">{String(memory.context?.symbol ?? '--')} · {String(memory.context?.mode ?? '--')} · {String(memory.context?.interval ?? '--')}</p>
                    <span className={`text-sm font-semibold ${toNumber(memory.realized_r) >= 0 ? 'text-teal-800' : 'text-rose-800'}`}>
                      {formatNumber(memory.realized_r)}R
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-stone-600">{String(memory.summary_text ?? '')}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-stone-500">
                    <span>{String(memory.learning_regime ?? '--')}</span>
                    <span>·</span>
                    <span>{String(memory.result_label ?? '--')}</span>
                    <span>·</span>
                    <span>{formatTime(memory.created_at_utc)}</span>
                  </div>
                </div>
              )) : <p className="text-sm text-stone-500">No trade memories built yet.</p>}
            </div>
          </section>

          <section className="rounded-[1.25rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <div className="flex items-center gap-2 text-sm font-semibold text-stone-950">
              <Radar className="h-4 w-4 text-teal-800" />
              Regime sample map
            </div>
            <div className="mt-4 grid gap-2">
              {regimeRows.length ? regimeRows.map(([regime, count]) => (
                <div key={regime} className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-[1rem] bg-stone-50/80 px-3 py-2">
                  <p className="text-sm text-stone-700">{regime}</p>
                  <span className="text-sm font-semibold text-stone-950">{formatNumber(count, 0)}</span>
                </div>
              )) : <p className="text-sm text-stone-500">No regime buckets populated yet.</p>}
            </div>
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <section className="rounded-[1.25rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Expectancy label profiles</h2>
            <div className="mt-4 grid gap-3">
              {expectancy.length ? expectancy.slice(0, 8).map((row) => (
                <div key={String(row.learning_regime)} className="rounded-[1rem] border border-stone-900/8 bg-stone-50/80 px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-stone-950">{String(row.learning_regime ?? '--')}</p>
                    <span className="text-sm text-stone-500">{formatNumber(row.samples, 0)} samples</span>
                  </div>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2 text-sm text-stone-600">
                    <span>Expected R: <strong className="text-stone-950">{formatNumber(row.expected_r)}</strong></span>
                    <span>Stop hit: <strong className="text-stone-950">{formatNumber(toNumber(row.stop_hit_probability) * 100)}%</strong></span>
                    <span>Target hit: <strong className="text-stone-950">{formatNumber(toNumber(row.target_hit_probability) * 100)}%</strong></span>
                    <span>Avg hold: <strong className="text-stone-950">{formatNumber(row.avg_hold_minutes, 0)}m</strong></span>
                  </div>
                </div>
              )) : <p className="text-sm text-stone-500">Expectancy labels are not populated yet.</p>}
            </div>
          </section>

          <section className="rounded-[1.25rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_12px_24px_rgba(77,62,40,0.06)]">
            <h2 className="text-sm font-semibold text-stone-950">Advisory top actions</h2>
            <div className="mt-4 grid gap-3">
              {topActions.length ? topActions.slice(0, 8).map((row, index) => (
                <div key={`${String(row.learning_regime)}-${String(row.action_label)}-${index}`} className="rounded-[1rem] border border-stone-900/8 bg-stone-50/80 px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-stone-950">{String(row.action_label ?? '--')}</p>
                    <span className={`text-sm font-semibold ${toNumber(row.avg_realized_r) >= 0 ? 'text-teal-800' : 'text-rose-800'}`}>{formatNumber(row.avg_realized_r)}R</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-stone-500">
                    <span>{String(row.learning_regime ?? '--')}</span>
                    <span>·</span>
                    <span>{formatNumber(row.count, 0)} samples</span>
                  </div>
                </div>
              )) : <p className="text-sm text-stone-500">No advisory action stats yet.</p>}
              {shadows.length ? (
                <div className="rounded-[1rem] border border-dashed border-stone-300 bg-stone-50/80 px-4 py-3">
                  <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Latest shadow call</p>
                  <p className="mt-2 text-sm font-semibold text-stone-950">{String(shadows[0]?.recommended_action ?? 'NO_RECOMMENDATION')}</p>
                  <p className="mt-1 text-sm text-stone-600">{String(shadows[0]?.reason_summary ?? '')}</p>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      </div>
    </AnimatedRoute>
  )
}
