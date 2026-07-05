import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'

import { KpiCard } from '../components/KpiCard'
import { ProfileScopeBar } from '../components/profile/ProfileScopeBar'
import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { fetchEngineHealthForScope, fetchJobs, fetchPortfolioForScope, fetchTradeOverview } from '../lib/api'
import { formatNumber } from '../lib/format'
import { useProfileScopeOptions } from '../hooks/useProfileScopeOptions'
import { DEFAULT_PROFILE_SCOPE, normalizeProfileScope, profileScopeToApiProfileId } from '../lib/profileScope'
import type { ProfileScopeValue } from '../lib/types'

export function TradeOverviewRoute() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { options: profileScopeOptions } = useProfileScopeOptions()
  const profileScope = normalizeProfileScope(searchParams.get('profile'), profileScopeOptions)
  const scopedProfileId = profileScopeToApiProfileId(profileScope, profileScopeOptions) ?? DEFAULT_PROFILE_SCOPE

  const overviewQuery = useQuery({ queryKey: ['trade-overview'], queryFn: fetchTradeOverview, refetchInterval: 30_000, refetchOnWindowFocus: false })
  const healthQuery = useQuery({ queryKey: ['engine-health', 'trade-overview', profileScope], queryFn: () => fetchEngineHealthForScope(profileScope), refetchInterval: 30_000, refetchOnWindowFocus: false })
  const jobsQuery = useQuery({ queryKey: ['scan-jobs', 'trade-overview'], queryFn: () => fetchJobs(20), refetchInterval: 30_000, refetchOnWindowFocus: false })
  const portfolioQuery = useQuery({ queryKey: ['portfolio', 'trade-overview', profileScope], queryFn: () => fetchPortfolioForScope(profileScope), refetchInterval: 30_000, refetchOnWindowFocus: false })

  const overview = overviewQuery.data
  const health = healthQuery.data
  const readiness = health?.runtime_readiness
  const jobs = jobsQuery.data
  const portfolio = portfolioQuery.data
  const resolvedProfileId = String(portfolio?.profile_id ?? portfolio?.paper_account?.profile_id ?? scopedProfileId)
  const resolvedAccountId = String(portfolio?.account_id ?? portfolio?.paper_account?.account_id ?? `${resolvedProfileId}:default`)
  const executionMode = resolvedProfileId.startsWith('paper-') ? 'PAPER' : 'UNKNOWN'
  const venue = resolvedProfileId.startsWith('paper-') ? 'paper' : 'unknown'
  const openTradeCount = Number(overview?.summary?.open_trade_count ?? portfolio?.open_positions?.length ?? portfolio?.portfolio?.open_orders ?? 0)
  const scopedBalance = Number(portfolio?.summary?.paper_balance ?? portfolio?.paper_account?.available_balance ?? 0)

  function handleProfileScopeChange(nextScope: ProfileScopeValue) {
    const nextParams = new URLSearchParams(searchParams)
    if (nextScope === DEFAULT_PROFILE_SCOPE) {
      nextParams.delete('profile')
    } else {
      nextParams.set('profile', nextScope)
    }
    setSearchParams(nextParams)
  }

  if (overviewQuery.isLoading && !overview) {
    return <AnimatedRoute><EmptyState message="Loading trade overview..." /></AnimatedRoute>
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
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Trade Overview</p>
          <h1 className="text-3xl font-semibold tracking-[-0.05em] text-stone-950">What needs operator attention right now.</h1>
          <p className="mt-2 text-sm text-stone-500">Summary-first operator posture with scoped portfolio/runtime context and compatibility-safe defaults.</p>
          <div className="mt-3 flex flex-wrap gap-2 text-sm text-stone-500">
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">Profile {resolvedProfileId}</span>
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">Account {resolvedAccountId}</span>
            <span className="rounded-full bg-stone-950/[0.03] px-3 py-2">{executionMode} · {venue}</span>
            <span className="rounded-full bg-amber-50 px-3 py-2 text-amber-900">Engine summary remains global until a later Phase 2 slice</span>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Active engine"
            value={String(readiness?.active_engine ?? health?.analyzer?.active_engine ?? overview?.engine?.active_engine ?? '--')}
            detail={`Champion: ${String(readiness?.champion_version ?? health?.analyzer?.active_engine_version ?? '--')}`}
          />
          <KpiCard
            label="Runtime state"
            value={String(readiness?.runtime_state ?? health?.runtime_status ?? 'UNKNOWN')}
            detail={`Fallback active: ${readiness?.fallback_active ? 'Yes' : 'No'}`}
          />
          <KpiCard
            label="Open trade count"
            value={formatNumber(openTradeCount, 0)}
            detail={`Pending jobs: ${formatNumber(jobs?.pending ?? 0, 0)}`}
          />
          <KpiCard
            label="Refresh cadence"
            value={`${formatNumber(overview?.summary?.refresh_seconds ?? 30, 0)}s`}
            detail={`Shadow: ${String(readiness?.shadow_status?.active ? readiness.shadow_status.engine_name ?? readiness.shadow_status.selected_engine ?? '--' : 'Disabled')}`}
          />
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          <KpiCard
            label="Selected profile"
            value={resolvedProfileId}
            detail={`Account: ${resolvedAccountId}`}
          />
          <KpiCard
            label="Execution identity"
            value={executionMode}
            detail={`Venue: ${venue}`}
          />
          <KpiCard
            label="Profile portfolio posture"
            value={formatNumber(scopedBalance, 2)}
            detail="Available balance in selected scope"
          />
        </section>
      </div>
    </AnimatedRoute>
  )
}
