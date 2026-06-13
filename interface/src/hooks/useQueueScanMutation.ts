import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'

import { queueLegacyScan } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import { profileScopeToApiProfileId } from '../lib/profileScope'
import type { QueueScanPayload } from '../lib/types'

export function useQueueScanMutation(profileScope?: string) {
  return useMutation({
    mutationFn: (payload: QueueScanPayload) => queueLegacyScan({
      ...payload,
      profile_id: payload.profile_id ?? profileScopeToApiProfileId(profileScope),
    }),
    onMutate: (payload) => {
      toast.loading('Queueing scan job...', {
        id: 'queue-scan-job',
        description: `${payload.symbols.length} symbols, ${payload.intervals.length} intervals, ${payload.modes.length} modes`,
      })
    },
    onSuccess: async (result) => {
      const job = (result.job ?? {}) as { id?: number | string }
      toast.success('Scan completed', {
        id: 'queue-scan-job',
        description: `Scan run #${job.id ?? '--'} finished in the Python runtime and the interface is refreshing.`,
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
        queryClient.invalidateQueries({ queryKey: ['logging-jobs'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
        queryClient.invalidateQueries({ queryKey: ['operator-alerts'] }),
      ])
    },
    onError: (error, payload) => {
      toast.error('Failed to queue scan job', {
        id: 'queue-scan-job',
        description: error instanceof Error ? error.message : `The Python scan runtime rejected ${payload.symbols.length} requested symbols.`,
      })
    },
  })
}
