import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'

import { retryFailedJobs } from '../lib/api'
import { queryClient } from '../lib/queryClient'

export function useRetryFailedJobsMutation() {
  return useMutation({
    mutationFn: (limit: number) => retryFailedJobs(limit),
    onMutate: () => {
      toast.loading('Retrying failed jobs...', {
        id: 'retry-failed-jobs',
      })
    },
    onSuccess: async (result) => {
      toast.success('Failed jobs re-queued', {
        id: 'retry-failed-jobs',
        description: `${result.retried ?? 0} jobs moved back into the queue.`,
      })
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (error) => {
      toast.error('Failed to retry jobs', {
        id: 'retry-failed-jobs',
        description: error instanceof Error ? error.message : 'The retry request did not complete.',
      })
    },
  })
}
