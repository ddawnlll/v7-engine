import { useQuery } from '@tanstack/react-query'

import { fetchRuntimeProfiles } from '../lib/api'
import type { RuntimeProfileListPayload } from '../lib/types'

type ProfileStatus = 'connected' | 'rate_limited' | 'error' | 'missing_credentials' | 'unknown' | 'not_applicable'

function profileStatus(profile: Record<string, unknown>): ProfileStatus {
  const connectivity = (profile.connectivity ?? {}) as Record<string, unknown>
  const status = String(connectivity.status ?? 'UNKNOWN').toUpperCase()
  if (status === 'CONNECTED' || status === 'READY') return 'connected'
  if (status === 'ERROR') return 'error'
  if (status === 'MISSING_CREDENTIALS') return 'missing_credentials'
  if (status === 'RATE_LIMITED') return 'rate_limited'
  if (status === 'NOT_APPLICABLE') return 'not_applicable'
  return 'unknown'
}

function statusColor(status: ProfileStatus): string {
  switch (status) {
    case 'connected':
      return 'bg-teal-500'
    case 'rate_limited':
      return 'bg-amber-500'
    case 'error':
    case 'missing_credentials':
      return 'bg-rose-500'
    case 'not_applicable':
      return 'bg-stone-400'
    default:
      return 'bg-stone-400'
  }
}

function statusLabel(status: ProfileStatus): string {
  switch (status) {
    case 'connected':
      return 'Connected'
    case 'rate_limited':
      return 'Rate limited'
    case 'error':
      return 'Error'
    case 'missing_credentials':
      return 'Missing credentials'
    case 'not_applicable':
      return 'N/A'
    default:
      return 'Unknown'
  }
}

function venueLabel(venue: string | null | undefined): string {
  const v = String(venue ?? '').toUpperCase()
  if (v === 'BINANCE' || v === 'BINANCE_USDM') return 'Binance'
  if (v === 'BYBIT') return 'Bybit'
  if (v === 'PAPER') return 'Paper'
  if (v === 'SIMULATION') return 'Simulation'
  return String(venue ?? 'unknown').replaceAll('_', ' ')
}

export function ProfileSelector() {
  const profilesQuery = useQuery({
    queryKey: ['runtime-profiles'],
    queryFn: fetchRuntimeProfiles,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })

  const payload = (profilesQuery.data ?? { items: [], count: 0 }) as RuntimeProfileListPayload
  const profiles = (payload.items ?? []) as Record<string, unknown>[]

  if (profilesQuery.isLoading && !profiles.length) {
    return (
      <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_14px_30px_rgba(77,62,40,0.06)]">
        <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Profile Status</p>
        <p className="mt-2 text-sm text-stone-500">Loading profiles...</p>
      </section>
    )
  }

  return (
    <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/84 p-4 shadow-[0_14px_30px_rgba(77,62,40,0.06)]">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="grid gap-1">
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Profile Status</p>
          <p className="text-sm text-stone-500">Execution profile connectivity and readiness</p>
        </div>
      </div>
      <div className="mt-3 grid gap-2">
        {profiles.length === 0 ? (
          <p className="text-sm text-stone-500">No profiles configured.</p>
        ) : (
          profiles.map((profile) => {
            const profileId = String(profile.profile_id ?? '')
            const name = String(profile.name ?? profileId)
            const venue = String(profile.venue ?? 'unknown')
            const status = profileStatus(profile)
            const executionMode = String(profile.execution_mode ?? profile.runtime_mode ?? 'UNKNOWN')
            const readOnly = Boolean(profile.read_only)
            const lastError = ((profile.connectivity as Record<string, unknown> | undefined)?.last_error as string | null) ?? null

            return (
              <div
                key={profileId}
                className="flex flex-wrap items-center justify-between gap-3 rounded-[1.2rem] border border-stone-900/8 bg-stone-950/[0.02] px-4 py-3"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusColor(status)}`} strokeWidth={0} />
                  <div className="grid min-w-0 gap-0.5">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold text-stone-950">{name}</span>
                      <span className="shrink-0 rounded-full bg-stone-950/[0.04] px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-wider text-stone-500">
                        {venueLabel(venue)}
                      </span>
                      {readOnly ? (
                        <span className="shrink-0 rounded-full bg-sky-50 px-2 py-0.5 text-[0.65rem] font-medium text-sky-700">
                          Read-only
                        </span>
                      ) : null}
                    </div>
                    <p className="truncate text-xs text-stone-500">
                      {executionMode} · {statusLabel(status)}
                      {lastError ? ` · ${lastError}` : ''}
                    </p>
                  </div>
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-1 text-[0.65rem] font-semibold uppercase tracking-wider ${
                  status === 'connected' ? 'bg-teal-50 text-teal-800' :
                  status === 'error' || status === 'missing_credentials' ? 'bg-rose-50 text-rose-800' :
                  status === 'rate_limited' ? 'bg-amber-50 text-amber-800' :
                  'bg-stone-100 text-stone-600'
                }`}>
                  {statusLabel(status)}
                </span>
              </div>
            )
          })
        )}
      </div>
    </section>
  )
}
