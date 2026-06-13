import { useMemo, useState } from 'react'

import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router-dom'

import { ProfileScopeBar } from '../components/profile/ProfileScopeBar'
import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { fetchEngineHealthForScope, fetchOperateChampion, fetchOperateModels, fetchOperateRuntimeStatus, fetchOperatorAlertsForScope, fetchPaperBalanceForScope, fetchRuntimeProfileReadOnlyExposure, fetchRuntimeSettingsForScope, promoteOperateCandidate, refreshOperateChampionRuntime, rollbackOperateChampion, syncRuntimeProfileReadOnly, updateOperateShadowEngine } from '../lib/api'
import { useProfileScopeOptions } from '../hooks/useProfileScopeOptions'
import { DEFAULT_PROFILE_SCOPE, normalizeProfileScope, profileScopeToApiProfileId, profileScopeToRuntimeProfileId } from '../lib/profileScope'
import type { ProfileScopeValue, RegistryModelSummaryPayload } from '../lib/types'

type ModelSortKey = 'expectancy_desc' | 'expectancy_asc' | 'win_rate_desc' | 'win_rate_asc' | 'sample_desc' | 'newest' | 'oldest' | 'name_asc' | 'name_desc'

export function OperateControlPageRoute() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { options: profileScopeOptions } = useProfileScopeOptions()
  const profileScope = normalizeProfileScope(searchParams.get('profile'), profileScopeOptions)
  const scopedProfileId = profileScopeToApiProfileId(profileScope, profileScopeOptions) ?? DEFAULT_PROFILE_SCOPE
  const runtimeProfileId = profileScopeToRuntimeProfileId(profileScope, profileScopeOptions) ?? scopedProfileId
  const isLiveReadOnlyScope = runtimeProfileId !== DEFAULT_PROFILE_SCOPE
  const [modelSearch, setModelSearch] = useState('')
  const [modelSort, setModelSort] = useState<ModelSortKey>('expectancy_desc')
  const championQuery = useQuery({ queryKey: ['operate-champion'], queryFn: fetchOperateChampion, refetchInterval: 10_000, refetchOnWindowFocus: false })
  const runtimeStatusQuery = useQuery({ queryKey: ['operate-runtime-status'], queryFn: fetchOperateRuntimeStatus, refetchInterval: 10_000, refetchOnWindowFocus: false })
  const modelsQuery = useQuery({ queryKey: ['operate-models'], queryFn: fetchOperateModels, refetchInterval: 10_000, refetchOnWindowFocus: false })
  const scopedHealthQuery = useQuery({ queryKey: ['engine-health', 'operate-control', profileScope], queryFn: () => fetchEngineHealthForScope(profileScope), refetchInterval: 10_000, refetchOnWindowFocus: false })
  const scopedPaperBalanceQuery = useQuery({
    queryKey: ['paper-balance', 'operate-control', profileScope],
    queryFn: () => fetchPaperBalanceForScope(profileScope),
    enabled: !isLiveReadOnlyScope,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })
  const scopedSettingsQuery = useQuery({ queryKey: ['runtime-settings', 'operate-control', profileScope], queryFn: () => fetchRuntimeSettingsForScope(profileScope), refetchInterval: 30_000, refetchOnWindowFocus: false })
  const scopedAlertsQuery = useQuery({ queryKey: ['operator-alerts', 'operate-control', profileScope], queryFn: () => fetchOperatorAlertsForScope(profileScope), refetchInterval: 30_000, refetchOnWindowFocus: false })
  const liveReadOnlyExposureQuery = useQuery({
    queryKey: ['runtime-profile-read-only-exposure', runtimeProfileId],
    queryFn: () => fetchRuntimeProfileReadOnlyExposure(runtimeProfileId),
    enabled: isLiveReadOnlyScope,
    refetchInterval: 10_000,
    refetchOnWindowFocus: false,
  })

  const syncLiveMutation = useMutation({
    mutationFn: () => syncRuntimeProfileReadOnly(runtimeProfileId),
    onSuccess: async () => {
      toast.success('Binance sync completed')
      await Promise.all([liveReadOnlyExposureQuery.refetch(), scopedHealthQuery.refetch()])
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Binance sync failed'),
  })

  const refreshChampionMutation = useMutation({
    mutationFn: () => refreshOperateChampionRuntime(),
    onSuccess: async () => {
      toast.success('Runtime champion refreshed')
      await Promise.all([championQuery.refetch(), runtimeStatusQuery.refetch(), modelsQuery.refetch()])
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Champion refresh failed'),
  })

  const shadowUpdateMutation = useMutation({
    mutationFn: (shadowEngine: string | null) => updateOperateShadowEngine(shadowEngine),
    onSuccess: async () => {
      toast.success('Shadow engine updated')
      await Promise.all([championQuery.refetch(), runtimeStatusQuery.refetch(), modelsQuery.refetch()])
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Shadow engine update failed'),
  })

  const promoteMutation = useMutation({
    mutationFn: (model: RegistryModelSummaryPayload) => promoteOperateCandidate({
      model_artifact_version: String(model.model_artifact_version ?? ''),
      expectancy_delta: Number(model.comparison_to_champion?.expectancy_r_delta ?? 0),
      win_rate: Number(model.metrics?.win_rate ?? 0),
      suppression_accuracy: 0,
      holdout_period_utc: String(model.training_timestamp_utc ?? new Date().toISOString()),
      paper_outcome_sample_size: Number(model.metrics?.sample_size ?? 0),
    }),
    onSuccess: async () => {
      toast.success('Model promoted')
      await Promise.all([championQuery.refetch(), runtimeStatusQuery.refetch(), modelsQuery.refetch()])
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Promotion failed'),
  })

  const rollbackMutation = useMutation({
    mutationFn: () => rollbackOperateChampion(),
    onSuccess: async () => {
      toast.success('Champion rolled back')
      await Promise.all([championQuery.refetch(), runtimeStatusQuery.refetch(), modelsQuery.refetch()])
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : 'Rollback failed'),
  })

  const champion = championQuery.data?.champion
  const runtime = runtimeStatusQuery.data
  const models = modelsQuery.data?.items ?? []
  const scopedHealth = scopedHealthQuery.data
  const scopedPaperBalance = scopedPaperBalanceQuery.data
  const scopedSettings = scopedSettingsQuery.data ?? {}
  const scopedAlerts = scopedAlertsQuery.data?.items ?? []
  const liveReadOnlyExposure = liveReadOnlyExposureQuery.data
  const liveProfile = (liveReadOnlyExposure?.profile ?? {}) as Record<string, unknown>
  const liveHealth = (liveReadOnlyExposure?.health ?? {}) as Record<string, unknown>
  const liveProtectiveSummary = (liveReadOnlyExposure?.protective_summary ?? {}) as Record<string, unknown>
  const resolvedProfileId = String(liveProfile.profile_id ?? scopedPaperBalance?.profile_id ?? runtimeProfileId)
  const resolvedAccountId = String(liveReadOnlyExposure?.account?.account_id ?? scopedPaperBalance?.account?.account_id ?? scopedPaperBalance?.account?.id ?? `${resolvedProfileId}:default`)
  const executionMode = String(liveProfile.execution_mode ?? (resolvedProfileId.startsWith('paper-') ? 'PAPER' : 'UNKNOWN'))
  const venue = String(liveProfile.venue ?? (resolvedProfileId.startsWith('paper-') ? 'paper' : 'unknown')).toLowerCase()
  const resolvedConfigHash = String(scopedPaperBalance?.resolved_config_hash ?? '').trim() || '--'
  const autonomousEnabled = String(scopedSettings.AUTONOMOUS_ENABLED ?? '').toLowerCase() === 'true'
  const scopedRuntimeState = String(liveHealth.exchange_status ?? scopedHealth?.runtime_readiness?.runtime_state ?? scopedHealth?.runtime_status ?? '--')
  const scopedLastSync = String(liveHealth.last_synced_at_utc ?? scopedHealth?.last_scan_completed_at_utc ?? '--')
  const scopedNextSync = String(scopedHealth?.next_scan_at_utc ?? '--')
  const selector = championQuery.data?.shadow_engine_selector
  const availableEngines = selector?.available_engines ?? championQuery.data?.available_engines ?? []

  const formatWinRate = (value?: number) => {
    if (value == null || Number.isNaN(value)) return '--'
    const normalized = value > 1 ? value : value * 100
    return `${normalized.toFixed(1)}%`
  }

  const formatExpectancy = (value?: number) => {
    if (value == null || Number.isNaN(value)) return '--'
    return `${value.toFixed(4)} R`
  }

  const filteredModels = useMemo(() => {
    const term = modelSearch.trim().toLowerCase()
    const next = models.filter((item) => {
      if (!term) return true
      const haystack = [
        String(item.model_artifact_version ?? ''),
        String(item.engine_name ?? ''),
        String(item.engine_version ?? ''),
        String(item.role ?? ''),
        String(item.dataset_name ?? ''),
        String(item.dataset_version ?? ''),
        String(item.feature_schema_version ?? ''),
        String(item.training_timestamp_utc ?? ''),
        ...((item.promotion_readiness?.blocking_reasons ?? []).map((value) => String(value))),
      ].join(' ').toLowerCase()
      return haystack.includes(term)
    })

    const sorted = [...next]
    const score = (value?: number | null) => Number(value ?? Number.NEGATIVE_INFINITY)
    sorted.sort((left, right) => {
      const leftExpectancy = score(left.metrics?.expectancy_r)
      const rightExpectancy = score(right.metrics?.expectancy_r)
      const leftWinRate = score(left.metrics?.win_rate)
      const rightWinRate = score(right.metrics?.win_rate)
      const leftSample = score(left.metrics?.sample_size)
      const rightSample = score(right.metrics?.sample_size)
      const leftName = String(left.model_artifact_version ?? '')
      const rightName = String(right.model_artifact_version ?? '')
      const leftTime = String(left.training_timestamp_utc ?? '')
      const rightTime = String(right.training_timestamp_utc ?? '')

      switch (modelSort) {
        case 'expectancy_asc':
          return leftExpectancy - rightExpectancy || rightWinRate - leftWinRate || rightTime.localeCompare(leftTime)
        case 'win_rate_desc':
          return rightWinRate - leftWinRate || rightExpectancy - leftExpectancy || rightTime.localeCompare(leftTime)
        case 'win_rate_asc':
          return leftWinRate - rightWinRate || rightExpectancy - leftExpectancy || rightTime.localeCompare(leftTime)
        case 'sample_desc':
          return rightSample - leftSample || rightExpectancy - leftExpectancy || rightTime.localeCompare(leftTime)
        case 'newest':
          return rightTime.localeCompare(leftTime) || rightExpectancy - leftExpectancy || rightWinRate - leftWinRate
        case 'oldest':
          return leftTime.localeCompare(rightTime) || rightExpectancy - leftExpectancy || rightWinRate - leftWinRate
        case 'name_asc':
          return leftName.localeCompare(rightName) || rightTime.localeCompare(leftTime)
        case 'name_desc':
          return rightName.localeCompare(leftName) || rightTime.localeCompare(leftTime)
        case 'expectancy_desc':
        default:
          return rightExpectancy - leftExpectancy || rightWinRate - leftWinRate || rightTime.localeCompare(leftTime)
      }
    })
    return sorted
  }, [modelSearch, modelSort, models])

  function handleProfileScopeChange(nextScope: ProfileScopeValue) {
    const nextParams = new URLSearchParams(searchParams)
    if (nextScope === DEFAULT_PROFILE_SCOPE) {
      nextParams.delete('profile')
    } else {
      nextParams.set('profile', nextScope)
    }
    setSearchParams(nextParams)
  }

  if ((championQuery.isLoading && !championQuery.data) || (modelsQuery.isLoading && !modelsQuery.data)) {
    return <AnimatedRoute><EmptyState message="Loading operate control..." /></AnimatedRoute>
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <ProfileScopeBar
          options={profileScopeOptions}
          value={profileScope}
          onChange={handleProfileScopeChange}
        />

        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-4 py-4 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Operate · Control</p>
          <h1 className="text-3xl font-semibold tracking-[-0.05em] text-stone-950">Champion registry actions and live engine binding.</h1>
          <div className="mt-3 flex flex-wrap gap-2 text-sm text-stone-500">
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">Profile {resolvedProfileId}</span>
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">Account {resolvedAccountId}</span>
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">{executionMode} · {venue}</span>
            <span className="rounded-full bg-amber-50 px-3 py-2 text-amber-900">Registry, champion, and model selection remain global until a later Phase 2 slice</span>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
            <div className="text-sm text-stone-500">Scoped runtime state</div>
            <div className="mt-2 text-xl font-semibold text-stone-950">{scopedRuntimeState}</div>
            <div className="mt-1 text-sm text-stone-500">Autonomous: {autonomousEnabled ? 'Enabled' : 'Disabled'}</div>
          </div>
          <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
            <div className="text-sm text-stone-500">Available balance</div>
            <div className="mt-2 text-xl font-semibold text-stone-950">${Number(liveReadOnlyExposure?.account?.available_balance ?? scopedPaperBalance?.balance ?? 0).toFixed(2)}</div>
            <div className="mt-1 text-sm text-stone-500">{isLiveReadOnlyScope ? `Read-only sync: ${String(liveHealth.rest_sync_status ?? '--')}` : `Resolved config hash: ${resolvedConfigHash}`}</div>
          </div>
          <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
            <div className="text-sm text-stone-500">Last sync</div>
            <div className="mt-2 text-xl font-semibold text-stone-950">{scopedLastSync === '--' ? '--' : 'Available'}</div>
            <div className="mt-1 text-sm text-stone-500">Last scan: {scopedLastSync}</div>
          </div>
          <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
            <div className="text-sm text-stone-500">Scoped alerts</div>
            <div className="mt-2 text-xl font-semibold text-stone-950">{String(scopedAlerts.length)}</div>
            <div className="mt-1 text-sm text-stone-500">Next scan: {scopedNextSync}</div>
          </div>
        </section>

        {isLiveReadOnlyScope ? (
          <section className="rounded-[1.4rem] border border-emerald-900/10 bg-emerald-50/60 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-stone-950">Live profile exposure</h2>
                <p className="text-sm text-stone-600">This surface is exposure-first for the selected live profile. Live placement controls are handled elsewhere.</p>
              </div>
              <span className="rounded-full bg-white px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-900">{String(liveHealth.exchange_status ?? 'unknown')}</span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-sm text-stone-700">
              <div>Connectivity: <span className="font-semibold text-stone-950">{String(liveHealth.connectivity_status ?? '--')}</span></div>
              <div>REST sync: <span className="font-semibold text-stone-950">{String(liveHealth.rest_sync_status ?? '--')}</span></div>
              <div>Stream: <span className="font-semibold text-stone-950">{String(liveHealth.stream_status ?? '--')}</span></div>
              <div>Reconciliation: <span className="font-semibold text-stone-950">{String(liveHealth.reconciliation_status ?? '--')}</span></div>
              <div>Open positions: <span className="font-semibold text-stone-950">{String(liveReadOnlyExposure?.positions?.length ?? 0)}</span></div>
              <div>Open orders: <span className="font-semibold text-stone-950">{String(liveReadOnlyExposure?.open_orders?.length ?? 0)}</span></div>
              <div>Protective orders: <span className="font-semibold text-stone-950">{String(liveProtectiveSummary.protective_open_order_count ?? 0)}</span></div>
              <div>Trailing stops: <span className="font-semibold text-stone-950">{String(liveProtectiveSummary.trailing_stop_order_count ?? 0)}</span></div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-sm text-stone-600">
              <button type="button" onClick={() => syncLiveMutation.mutate()} disabled={syncLiveMutation.isPending} className="rounded-full border border-stone-900/8 bg-white px-3 py-2 font-semibold text-stone-950 disabled:opacity-60">
                {syncLiveMutation.isPending ? 'Syncing Binance…' : 'Sync Binance now'}
              </button>
              <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-[0.72rem] font-semibold uppercase tracking-[0.16em] ${syncLiveMutation.isPending ? 'border-amber-700/15 bg-amber-600/10 text-amber-900' : String(liveHealth.rest_sync_status ?? '').toUpperCase() === 'SYNCED' ? 'border-teal-800/15 bg-teal-700/8 text-teal-900' : 'border-stone-900/10 bg-stone-950/[0.03] text-stone-700'}`}>
                {syncLiveMutation.isPending ? 'SYNCING' : String(liveHealth.rest_sync_status ?? 'UNKNOWN')}
              </span>
              <span className="rounded-full bg-white px-3 py-2">Last REST sync: {String(liveHealth.last_synced_at_utc ?? '--')}</span>
              <span className="rounded-full bg-white px-3 py-2">Last stream event: {String(liveHealth.last_event_seen_at_utc ?? '--')}</span>
              <span className="rounded-full bg-white px-3 py-2">Last reconciled: {String(liveHealth.last_reconciled_at_utc ?? '--')}</span>
              <span className="rounded-full bg-white px-3 py-2">Take profit orders: {String(liveProtectiveSummary.take_profit_order_count ?? 0)}</span>
              <span className="rounded-full bg-white px-3 py-2">Stop loss orders: {String(liveProtectiveSummary.stop_loss_order_count ?? 0)}</span>
            </div>
          </section>
        ) : null}

        <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-stone-950">Runtime readiness</h2>
            <button type="button" onClick={() => refreshChampionMutation.mutate()} className="rounded-full border border-stone-900/8 px-4 py-2 text-sm font-semibold text-stone-950">Refresh champion</button>
          </div>
          {!runtime ? <div className="mt-4"><EmptyState message="No runtime readiness data available." /></div> : (
            <div className="mt-4 grid gap-3 text-sm text-stone-700 md:grid-cols-2 xl:grid-cols-4">
              <div>Active engine: <span className="font-semibold text-stone-950">{String(runtime.active_engine ?? '--')}</span></div>
              <div>Champion version: <span className="font-semibold text-stone-950">{String(runtime.champion_version ?? '--')}</span></div>
              <div>Fallback active: <span className="font-semibold text-stone-950">{runtime.fallback_active ? 'Yes' : 'No'}</span></div>
              <div>Runtime state: <span className="font-semibold text-stone-950">{String(runtime.runtime_state ?? '--')}</span></div>
              <div>Active engine version: <span className="font-semibold text-stone-950">{String(runtime.active_engine_version ?? '--')}</span></div>
              <div>Shadow engine: <span className="font-semibold text-stone-950">{runtime.shadow_status?.active ? `${String(runtime.shadow_status.engine_name ?? runtime.shadow_status.selected_engine ?? '--')} ${String(runtime.shadow_status.engine_version ?? '')}` : 'Disabled'}</span></div>
              <div>Health: <span className="font-semibold text-stone-950">{runtime.healthy ? 'Healthy' : 'Degraded'}</span></div>
              <div>Consecutive failures: <span className="font-semibold text-stone-950">{String(runtime.consecutive_failures ?? 0)}</span></div>
            </div>
          )}
        </section>

        <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-stone-950">Active champion</h2>
            <button type="button" onClick={() => rollbackMutation.mutate()} className="rounded-full bg-stone-950 px-4 py-2 text-sm font-semibold text-white">Rollback</button>
          </div>
          {!champion ? <div className="mt-4"><EmptyState message="No active champion registered." /></div> : (
            <div className="mt-4 grid gap-3 text-sm text-stone-700">
              <div>Artifact: <span className="font-semibold text-stone-950">{String(champion.model_artifact_version ?? '--')}</span></div>
              <div>Engine: <span className="font-semibold text-stone-950">{String(champion.engine_name ?? '--')} {String(champion.engine_version ?? '')}</span></div>
              <div className="grid gap-2">
                <label className="text-sm font-semibold text-stone-950" htmlFor="shadow-engine-selector">Shadow engine</label>
                {selector?.supported === false ? (
                  <div className="text-stone-500">Shadow engine selection is currently unavailable in this runtime.</div>
                ) : (
                  <select
                    id="shadow-engine-selector"
                    className="max-w-md rounded-[0.9rem] border border-stone-900/10 bg-white px-3 py-2"
                    value={String(selector?.selected_engine ?? championQuery.data?.shadow_engine ?? '')}
                    onChange={(event) => shadowUpdateMutation.mutate(event.target.value || null)}
                    disabled={shadowUpdateMutation.isPending}
                  >
                    <option value="">Disabled</option>
                    {availableEngines.map((item) => {
                      const engineName = String(item.engine_name ?? '')
                      return <option key={engineName} value={engineName}>{engineName} {String(item.engine_version ?? '')}</option>
                    })}
                  </select>
                )}
              </div>
            </div>
          )}
        </section>

        <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-stone-950">Available models</h2>
              <p className="text-sm text-stone-500">Search, sort, and promote any active-eligible model.</p>
            </div>
            <div className="text-sm text-stone-500">{filteredModels.length} of {models.length} model{models.length === 1 ? '' : 's'}</div>
          </div>
          {!models.length ? <div className="mt-4"><EmptyState message="No registry models available." /></div> : (
            <div className="mt-4 grid gap-3">
              <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
                <input
                  type="search"
                  value={modelSearch}
                  onChange={(event) => setModelSearch(event.target.value)}
                  placeholder="Search by version, engine, dataset, role, blocker..."
                  className="rounded-[0.9rem] border border-stone-900/10 bg-white px-3 py-2 text-sm text-stone-950 outline-none ring-0 placeholder:text-stone-400"
                />
                <select
                  value={modelSort}
                  onChange={(event) => setModelSort(event.target.value as ModelSortKey)}
                  className="rounded-[0.9rem] border border-stone-900/10 bg-white px-3 py-2 text-sm text-stone-950"
                >
                  <option value="expectancy_desc">Sort: Expectancy ↓</option>
                  <option value="expectancy_asc">Sort: Expectancy ↑</option>
                  <option value="win_rate_desc">Sort: Win rate ↓</option>
                  <option value="win_rate_asc">Sort: Win rate ↑</option>
                  <option value="sample_desc">Sort: Sample size ↓</option>
                  <option value="newest">Sort: Newest first</option>
                  <option value="oldest">Sort: Oldest first</option>
                  <option value="name_asc">Sort: Name A → Z</option>
                  <option value="name_desc">Sort: Name Z → A</option>
                </select>
              </div>
              {!filteredModels.length ? <EmptyState message="No models match the current search/filter." /> : filteredModels.map((item) => {
                const version = String(item.model_artifact_version ?? 'model')
                const isChampion = version === champion?.model_artifact_version
                const activeEligible = item.promotion_readiness?.active_eligible !== false
                const blockers = item.promotion_readiness?.blocking_reasons ?? []
                const winRate = formatWinRate(item.metrics?.win_rate)
                const expectancy = formatExpectancy(item.metrics?.expectancy_r)
                const deltaR = item.comparison_to_champion?.expectancy_r_delta
                return (
                  <div key={version} className="grid gap-3 rounded-[1rem] border border-stone-900/8 bg-white px-4 py-3 text-sm md:grid-cols-[1fr_auto] md:items-center">
                    <div className="grid gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="font-semibold text-stone-950">{version}</div>
                        <span className={`rounded-full px-2 py-1 text-[0.7rem] font-semibold uppercase tracking-[0.14em] ${isChampion ? 'bg-emerald-100 text-emerald-800' : activeEligible ? 'bg-teal-100 text-teal-800' : 'bg-amber-100 text-amber-800'}`}>
                          {isChampion ? 'Champion' : activeEligible ? 'Selectable' : 'Blocked'}
                        </span>
                      </div>
                      <div className="text-stone-500">{String(item.engine_name ?? '--')} {String(item.engine_version ?? '')} · {String(item.role ?? '--')}</div>
                      <div className="flex flex-wrap gap-4 text-stone-700">
                        <div>Win rate: <span className="font-semibold text-stone-950">{winRate}</span></div>
                        <div>Expectancy: <span className="font-semibold text-stone-950">{expectancy}</span></div>
                        <div>Sample: <span className="font-semibold text-stone-950">{String(item.metrics?.sample_size ?? '--')}</span></div>
                        <div>ΔR vs champ: <span className="font-semibold text-stone-950">{deltaR == null ? '--' : formatExpectancy(deltaR)}</span></div>
                      </div>
                      {!activeEligible && blockers.length > 0 ? <div className="text-amber-700">Blocked: {blockers.join(', ')}</div> : null}
                    </div>
                    <div className="flex flex-col gap-2 md:items-end">
                      <button
                        type="button"
                        onClick={() => promoteMutation.mutate(item)}
                        disabled={!activeEligible || isChampion || promoteMutation.isPending}
                        className="rounded-full border border-stone-900/8 px-4 py-2 font-semibold text-stone-900 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isChampion ? 'Current champion' : 'Use this model'}
                      </button>
                      <div className="text-xs text-stone-500">{String(item.training_timestamp_utc ?? '')}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </AnimatedRoute>
  )
}
