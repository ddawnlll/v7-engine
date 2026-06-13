import { useQuery } from '@tanstack/react-query'

import { fetchRuntimeProfiles } from '../lib/api'
import { buildProfileScopeOptions } from '../lib/profileScope'

export function useProfileScopeOptions() {
  const runtimeProfilesQuery = useQuery({
    queryKey: ['runtime-profiles', 'scope-options'],
    queryFn: fetchRuntimeProfiles,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  return {
    ...runtimeProfilesQuery,
    options: buildProfileScopeOptions(runtimeProfilesQuery.data?.items),
  }
}
