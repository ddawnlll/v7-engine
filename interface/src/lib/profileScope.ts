import { getCurrentSettings } from './runtimeSettings'
import type { ProfileScopeOption, ProfileScopeValue, RuntimeProfileSummary } from './types'

export const DEFAULT_PROFILE_SCOPE: ProfileScopeValue = 'paper-main'

const DEFERRED_SCOPE_OPTIONS: ProfileScopeOption[] = [
  {
    value: 'all-profiles',
    label: 'All profiles',
    kind: 'aggregate',
    enabled: false,
    description: 'Aggregate profile scope will land in a later Phase 2 slice.',
  },
  {
    value: 'shared-learning',
    label: 'Shared learning',
    kind: 'shared-learning',
    enabled: false,
    description: 'Shared-learning scope is deferred beyond the first Trades adoption slice.',
  },
]

function describeRuntimeProfile(profile: RuntimeProfileSummary): string {
  const executionMode = String(profile.execution_mode ?? profile.runtime_mode ?? 'UNKNOWN').toUpperCase()
  const venue = String(profile.venue ?? 'UNKNOWN').replaceAll('_', ' ')
  const readOnly = profile.read_only ? 'Read-only' : 'Interactive'
  return `${executionMode} · ${venue} · ${readOnly}`
}

function mapRuntimeProfileOption(profile: RuntimeProfileSummary): ProfileScopeOption | null {
  const profileId = String(profile.profile_id ?? '').trim()
  if (!profileId) return null
  return {
    value: profileId,
    profile_id: profileId,
    label: profileId,
    kind: 'profile',
    enabled: true,
    description: describeRuntimeProfile(profile),
  }
}

export function buildProfileScopeOptions(runtimeProfiles?: RuntimeProfileSummary[] | null): ProfileScopeOption[] {
  const dynamicProfiles = (runtimeProfiles ?? [])
    .map(mapRuntimeProfileOption)
    .filter((option): option is ProfileScopeOption => option != null)

  if (!dynamicProfiles.some((option) => option.value === DEFAULT_PROFILE_SCOPE)) {
    dynamicProfiles.unshift({
      value: DEFAULT_PROFILE_SCOPE,
      profile_id: DEFAULT_PROFILE_SCOPE,
      label: DEFAULT_PROFILE_SCOPE,
      kind: 'profile',
      enabled: true,
      description: 'Current compatibility profile.',
    })
  }

  return [...DEFERRED_SCOPE_OPTIONS, ...dynamicProfiles]
}

export const PROFILE_SCOPE_OPTIONS: ProfileScopeOption[] = buildProfileScopeOptions()

function validScopeValues(options: ProfileScopeOption[]): Set<string> {
  return new Set(options.map((option) => option.value))
}

function isDeferredScopeValue(value: string): boolean {
  return value === 'all-profiles' || value === 'shared-learning'
}

export function normalizeProfileScope(rawValue: string | null | undefined, options: ProfileScopeOption[] = PROFILE_SCOPE_OPTIONS): ProfileScopeValue {
  const candidate = String(rawValue ?? '').trim()
  return validScopeValues(options).has(candidate) ? candidate : DEFAULT_PROFILE_SCOPE
}

export function getProfileScopeOption(value: string | null | undefined, options: ProfileScopeOption[] = PROFILE_SCOPE_OPTIONS): ProfileScopeOption {
  const normalized = normalizeProfileScope(value, options)
  return options.find((option) => option.value === normalized) ?? options.find((option) => option.value === DEFAULT_PROFILE_SCOPE) ?? PROFILE_SCOPE_OPTIONS[0]
}

export function profileScopeToApiProfileId(value: string | null | undefined, options: ProfileScopeOption[] = PROFILE_SCOPE_OPTIONS): string | undefined {
  const candidate = String(value ?? '').trim()
  if (!candidate || isDeferredScopeValue(candidate)) return undefined
  const option = options.find((item) => item.value === candidate)
  if (option) {
    if (option.kind !== 'profile' || !option.enabled) return undefined
    return option.profile_id ?? option.value
  }
  return candidate
}

export function profileScopeToRuntimeProfileId(value: string | null | undefined, options: ProfileScopeOption[] = PROFILE_SCOPE_OPTIONS): string | undefined {
  return profileScopeToApiProfileId(value, options)
}

export function withCurrentProfileScope(to: string, currentSearch: string): string {
  const [pathname, rawSearch = ''] = to.split('?')
  const currentParams = new URLSearchParams(currentSearch)
  const nextParams = new URLSearchParams(rawSearch)
  const currentProfile = currentParams.get('profile') || getCurrentSettings().preferredProfileScope

  if (currentProfile && !nextParams.has('profile') && currentProfile !== DEFAULT_PROFILE_SCOPE) {
    nextParams.set('profile', currentProfile)
  }

  const mergedSearch = nextParams.toString()
  return mergedSearch ? `${pathname}?${mergedSearch}` : pathname
}
