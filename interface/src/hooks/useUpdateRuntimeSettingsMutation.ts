import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'

import { updateRuntimeSettings } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import type { RuntimeSettingsPayload } from '../lib/types'

export function useUpdateRuntimeSettingsMutation() {
  return useMutation({
    mutationFn: (payload: RuntimeSettingsPayload) => updateRuntimeSettings(payload),
    onMutate: () => {
      toast.loading('Saving runtime settings...', {
        id: 'save-runtime-settings',
      })
    },
    onSuccess: async () => {
      toast.success('Runtime settings updated', {
        id: 'save-runtime-settings',
        description: 'The engine settings were saved and the dashboard snapshot is refreshing.',
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['runtime-settings'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['learning-profile'] }),
        queryClient.invalidateQueries({ queryKey: ['learning-effectiveness'] }),
        queryClient.invalidateQueries({ queryKey: ['self-learning-status'] }),
        queryClient.invalidateQueries({ queryKey: ['self-learning-profile'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to save runtime settings', {
        id: 'save-runtime-settings',
        description: error instanceof Error ? error.message : 'The settings update request did not complete.',
      })
    },
  })
}
