import { useMutation } from '@tanstack/react-query'
import { toast } from 'sonner'

import { updateRuntimeProfileSettings } from '../lib/api'
import { queryClient } from '../lib/queryClient'
import type { RuntimeProfileSettingsUpdatePayload } from '../lib/types'

export function useUpdateRuntimeProfileSettingsMutation() {
  return useMutation({
    mutationFn: (payload: RuntimeProfileSettingsUpdatePayload) => updateRuntimeProfileSettings(payload),
    onMutate: () => {
      toast.loading('Saving profile settings...', {
        id: 'save-runtime-profile-settings',
      })
    },
    onSuccess: async () => {
      toast.success('Profile settings updated', {
        id: 'save-runtime-profile-settings',
        description: 'The selected profile posture and policy snapshot is refreshing.',
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['runtime-profile-settings'] }),
        queryClient.invalidateQueries({ queryKey: ['runtime-profiles'] }),
        queryClient.invalidateQueries({ queryKey: ['runtime-settings'] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
      ])
    },
    onError: (error) => {
      toast.error('Failed to save profile settings', {
        id: 'save-runtime-profile-settings',
        description: error instanceof Error ? error.message : 'The profile settings update request did not complete.',
      })
    },
  })
}
