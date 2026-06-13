import { useIsMutating, useQuery } from '@tanstack/react-query'
import type { UseQueryOptions } from '@tanstack/react-query'

import { fetchDashboard } from '../lib/api'
import type { DashboardPayload } from '../lib/types'

export function useDashboardQuery(options?: Omit<UseQueryOptions<DashboardPayload, Error>, 'queryKey' | 'queryFn'>) {
  const storageWritesInFlight = useIsMutating({ mutationKey: ['storage-write'] })
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    enabled: options?.enabled !== false && storageWritesInFlight === 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 60_000,
    ...options,
  })
}
