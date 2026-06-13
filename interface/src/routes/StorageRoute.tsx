import { useMemo, useState } from 'react'

import { useSearchParams } from 'react-router-dom'

import { useMutation, useQuery } from '@tanstack/react-query'
import { Copy, Database, Download, HardDriveDownload, HardDriveUpload, RefreshCw, RotateCcw, ShieldAlert } from 'lucide-react'
import { toast } from 'sonner'

import { ProfileScopeBar } from '../components/profile/ProfileScopeBar'
import { AnimatedRoute } from '../components/ui/AnimatedRoute'
import { EmptyState } from '../components/ui/EmptyState'
import { JsonViewer } from '../components/ui/JsonViewer'
import {
  clearStorageComponents,
  clearStorageGroup,
  clearStorage,
  deleteStorageTrashEntry,
  exportStorage,
  fetchStorageStatus,
  fetchStorageTrash,
  importStorage,
  pauseScans,
  seedStorage,
  stopScans,
} from '../lib/api'
import { useProfileScopeOptions } from '../hooks/useProfileScopeOptions'
import { DEFAULT_PROFILE_SCOPE, normalizeProfileScope } from '../lib/profileScope'
import { copyToClipboard, downloadFile, exportFilename } from '../lib/export'
import { compactNumber, formatTime } from '../lib/format'
import { queryClient } from '../lib/queryClient'
import type { JsonRecord, ProfileScopeValue, StorageExportPayload, StorageMutationSummary, StorageStatusPayload, StorageTrashEntry } from '../lib/types'

type StorageSeedMode = 'seed' | 'all' | 'real'
type ActionState = {
  kind: 'idle' | 'export' | 'import' | 'seed' | 'clear'
  status: 'idle' | 'pending' | 'success' | 'error'
  title: string
  message: string
  startedAt?: string
  finishedAt?: string
}

function humanLabel(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (match) => match.toUpperCase())
}

function summarizeCounts(value: Record<string, number> | undefined, limit = 6) {
  const items = Object.entries(value ?? {}).filter(([, count]) => Number.isFinite(count))
  if (!items.length) return 'No counters available.'
  return items
    .slice(0, limit)
    .map(([key, count]) => `${humanLabel(key)} ${compactNumber(count)}`)
    .join(' · ')
}

function backendTone(healthy: boolean | undefined) {
  if (healthy === true) return 'border-teal-900/10 bg-teal-50/90 text-teal-900'
  if (healthy === false) return 'border-rose-900/10 bg-rose-50/90 text-rose-900'
  return 'border-stone-900/8 bg-white text-stone-700'
}

function actionTone(status: ActionState['status']) {
  if (status === 'success') return 'border-teal-900/10 bg-teal-50/90 text-teal-900'
  if (status === 'error') return 'border-rose-900/10 bg-rose-50/90 text-rose-900'
  if (status === 'pending') return 'border-amber-900/10 bg-amber-50/90 text-amber-900'
  return 'border-stone-900/8 bg-white text-stone-700'
}

const PROTECTED_FAILURE_COMPONENTS = new Set(['trade_failures', 'alerts', 'performance_snapshots', 'circuit_breaker_events'])
const PROTECTED_LEARNING_COMPONENTS = new Set([
  'trade_memories',
  'self_learning_runs',
  'counterfactual_replays',
  'policy_examples',
  'expectancy_label_profiles',
  'shadow_policy_decisions',
  'engine_run_manifests',
  'improvement_change_events',
  'signal_component_attributions',
  'trade_component_outcomes',
])

function protectedConfirmPhraseForComponents(components: string[]) {
  const phrases: string[] = []
  if (components.some((component) => PROTECTED_FAILURE_COMPONENTS.has(component))) phrases.push('DELETE FAILURE DATA')
  if (components.some((component) => PROTECTED_LEARNING_COMPONENTS.has(component))) phrases.push('DELETE LEARNING DATA')
  return phrases.join(' ')
}

export function StorageRoute() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { options: profileScopeOptions } = useProfileScopeOptions()
  const profileScope = normalizeProfileScope(searchParams.get('profile'), profileScopeOptions)
  const isScopedProfile = profileScope !== DEFAULT_PROFILE_SCOPE
  const [importText, setImportText] = useState('')
  const [confirmText, setConfirmText] = useState('')
  const [clearConfirmText, setClearConfirmText] = useState('')
  const [componentSearch, setComponentSearch] = useState('')
  const [selectedComponents, setSelectedComponents] = useState<string[]>([])
  const [actionState, setActionState] = useState<ActionState>({
    kind: 'idle',
    status: 'idle',
    title: 'No action running',
    message: 'Storage actions will report their status here.',
  })

  async function refreshStorageViews() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['storage-status'] }),
      queryClient.invalidateQueries({ queryKey: ['storage-trash'] }),
      queryClient.invalidateQueries({ queryKey: ['engine-health'] }),
      queryClient.invalidateQueries({ queryKey: ['orders-ledger'] }),
      queryClient.invalidateQueries({ queryKey: ['trade-failures', 'trades'] }),
      queryClient.invalidateQueries({ queryKey: ['scan-jobs'] }),
      queryClient.invalidateQueries({ queryKey: ['scan-jobs-history'] }),
      queryClient.invalidateQueries({ queryKey: ['trade-analytics'] }),
      queryClient.invalidateQueries({ queryKey: ['improvement-analytics'] }),
      queryClient.invalidateQueries({ queryKey: ['failure-analytics-page'] }),
      queryClient.invalidateQueries({ queryKey: ['failure-analytics-circuit-events'] }),
      queryClient.invalidateQueries({ queryKey: ['failure-analytics-self-learning'] }),
      queryClient.invalidateQueries({ queryKey: ['self-learning-status'] }),
      queryClient.invalidateQueries({ queryKey: ['self-learning-profile'] }),
      queryClient.invalidateQueries({ queryKey: ['self-learning-memories'] }),
      queryClient.invalidateQueries({ queryKey: ['learning-profile', 'admin'] }),
      queryClient.invalidateQueries({ queryKey: ['learning-effectiveness', 'admin'] }),
      queryClient.invalidateQueries({ queryKey: ['failures', 'admin'] }),
      queryClient.invalidateQueries({ queryKey: ['failure-summary', 'admin'] }),
      queryClient.invalidateQueries({ queryKey: ['weakness-profile', 'admin'] }),
      queryClient.invalidateQueries({ queryKey: ['operator-alerts', 'admin'] }),
      queryClient.invalidateQueries({ queryKey: ['operator-alerts', 'app-shell'] }),
      queryClient.invalidateQueries({ queryKey: ['circuit-breaker-state', 'admin'] }),
      queryClient.invalidateQueries({ queryKey: ['circuit-breaker-events', 'admin'] }),
      queryClient.invalidateQueries({ queryKey: ['circuit-breaker-state', 'app-shell'] }),
      queryClient.invalidateQueries({ queryKey: ['market-overview'] }),
      queryClient.invalidateQueries({ queryKey: ['market-signals'] }),
      queryClient.invalidateQueries({ queryKey: ['paper-balance'] }),
      queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
      queryClient.invalidateQueries({ queryKey: ['portfolio', 'app-shell'] }),
    ])
  }

  const statusQuery = useQuery({
    queryKey: ['storage-status', profileScope],
    queryFn: () => fetchStorageStatus(profileScope),
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })

  const trashQuery = useQuery({
    queryKey: ['storage-trash'],
    queryFn: fetchStorageTrash,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
  })

  const parsedImport = useMemo(() => {
    const trimmed = importText.trim()
    if (!trimmed) return null
    try {
      return JSON.parse(trimmed) as JsonRecord
    } catch {
      return null
    }
  }, [importText])

  const importPreviewQuery = useQuery({
    queryKey: ['storage-import-preview', importText],
    queryFn: () => importStorage('postgres', parsedImport as JsonRecord, true),
    enabled: Boolean(parsedImport),
    refetchOnWindowFocus: false,
    staleTime: 0,
  })

  const exportMutation = useMutation({
    mutationFn: () => exportStorage('postgres', profileScope),
    onMutate: () => {
      setActionState({
        kind: 'export',
        status: 'pending',
        title: 'Export in progress',
        message: 'Exporting PostgreSQL operational state.',
        startedAt: new Date().toISOString(),
      })
    },
    onSuccess: (payload) => {
      const result = payload as StorageExportPayload
      setActionState({
        kind: 'export',
        status: 'success',
        title: 'Export complete',
        message: summarizeCounts(result.counts),
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      downloadFile(JSON.stringify(payload, null, 2), exportFilename('postgres-storage-export', 'json'), 'application/json')
      toast.success('PostgreSQL export downloaded.')
    },
    onError: (error) => {
      setActionState({
        kind: 'export',
        status: 'error',
        title: 'Export failed',
        message: error instanceof Error ? error.message : 'Storage export failed.',
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      toast.error(error instanceof Error ? error.message : 'Storage export failed.')
    },
  })

  const importMutation = useMutation({
    mutationFn: ({ payload, confirmPhrase }: { payload: JsonRecord; confirmPhrase?: string }) => importStorage('postgres', payload, false, confirmPhrase),
    onMutate: () => {
      setActionState({
        kind: 'import',
        status: 'pending',
        title: 'Import in progress',
        message: 'Replacing PostgreSQL operational state from the provided JSON.',
        startedAt: new Date().toISOString(),
      })
    },
    onSuccess: (summary) => {
      const result = summary as StorageMutationSummary
      setActionState({
        kind: 'import',
        status: 'success',
        title: 'Import complete',
        message: summarizeCounts(result.current_counts),
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      setImportText('')
      setConfirmText('')
      void refreshStorageViews()
      toast.success('PostgreSQL import complete.')
    },
    onError: (error) => {
      setActionState({
        kind: 'import',
        status: 'error',
        title: 'Import failed',
        message: error instanceof Error ? error.message : 'Storage import failed.',
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      toast.error(error instanceof Error ? error.message : 'Storage import failed.')
    },
  })

  const seedMutation = useMutation({
    mutationFn: ({ mode, confirmPhrase }: { mode: StorageSeedMode; confirmPhrase?: string }) => seedStorage('postgres', mode, confirmPhrase),
    onMutate: ({ mode }) => {
      setActionState({
        kind: 'seed',
        status: 'pending',
        title: `${mode === 'real' ? 'Reset' : 'Seed'} in progress`,
        message: mode === 'real' ? 'Clearing seeded operational rows and preserving runtime settings.' : 'Applying PostgreSQL seed data.',
        startedAt: new Date().toISOString(),
      })
    },
    onSuccess: (summary) => {
      const result = summary as StorageMutationSummary
      setActionState({
        kind: 'seed',
        status: 'success',
        title: `${String(result.mode ?? 'seed')} complete`,
        message: summarizeCounts(result.current_counts),
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      void refreshStorageViews()
      toast.success(`PostgreSQL ${String(result.mode ?? 'seed')} complete.`)
    },
    onError: (error) => {
      setActionState({
        kind: 'seed',
        status: 'error',
        title: 'Seed failed',
        message: error instanceof Error ? error.message : 'Storage seed failed.',
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      toast.error(error instanceof Error ? error.message : 'Storage seed failed.')
    },
  })

  const clearMutation = useMutation({
    mutationFn: ({ confirmPhrase }: { confirmPhrase?: string } = {}) => clearStorage('postgres', false, profileScope, confirmPhrase),
    onMutate: () => {
      setActionState({
        kind: 'clear',
        status: 'pending',
        title: 'Database clear in progress',
        message: 'Deleting all PostgreSQL operational rows and runtime settings.',
        startedAt: new Date().toISOString(),
      })
    },
    onSuccess: (summary) => {
      const result = summary as StorageMutationSummary
      setActionState({
        kind: 'clear',
        status: 'success',
        title: 'Database cleared',
        message: summarizeCounts(result.current_counts),
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      setClearConfirmText('')
      void refreshStorageViews()
      toast.success('PostgreSQL database cleared.')
    },
    onError: (error) => {
      setActionState({
        kind: 'clear',
        status: 'error',
        title: 'Database clear failed',
        message: error instanceof Error ? error.message : 'Database clear failed.',
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      toast.error(error instanceof Error ? error.message : 'Database clear failed.')
    },
  })

  const deleteTrashMutation = useMutation({
    mutationFn: ({ trashId, confirmPhrase }: { trashId: string; confirmPhrase: string }) => deleteStorageTrashEntry(trashId, confirmPhrase),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['storage-trash'] })
      toast.success('Trash entry deleted forever.')
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Trash deletion failed.')
    },
  })

  const clearGroupMutation = useMutation({
    mutationFn: ({ groupId, components, confirmPhrase }: { groupId?: string; components?: string[]; confirmPhrase?: string }) => {
      if (groupId) return clearStorageGroup('postgres', groupId, profileScope, confirmPhrase)
      return clearStorageComponents('postgres', components ?? [], profileScope, confirmPhrase)
    },
    onMutate: (variables) => {
      setActionState({
        kind: 'clear',
        status: 'pending',
        title: variables.groupId ? `Clearing ${variables.groupId}` : 'Clearing selected components',
        message: variables.components?.length ? variables.components.join(', ') : 'Deleting selected storage components.',
        startedAt: new Date().toISOString(),
      })
    },
    onSuccess: (summary) => {
      const result = summary as StorageMutationSummary
      setActionState({
        kind: 'clear',
        status: 'success',
        title: result.cleared_group ? `${result.cleared_group} cleared` : 'Selected components cleared',
        message: (result.cleared_components ?? []).join(', ') || summarizeCounts(result.current_counts),
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      void refreshStorageViews()
      toast.success(result.cleared_group ? `${result.cleared_group} cleared.` : 'Selected storage components cleared.')
    },
    onError: (error) => {
      setActionState({
        kind: 'clear',
        status: 'error',
        title: 'Selective clear failed',
        message: error instanceof Error ? error.message : 'Selective clear failed.',
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      toast.error(error instanceof Error ? error.message : 'Selective clear failed.')
    },
  })

  async function handleCopyExport() {
    const payload = await exportMutation.mutateAsync()
    await copyToClipboard(JSON.stringify(payload, null, 2))
    toast.success('PostgreSQL export copied.')
  }

  function handleImport() {
    if (!parsedImport) {
      toast.error('Paste valid JSON before importing.')
      return
    }
    if (confirmText.trim().toUpperCase() !== 'IMPORT') {
      toast.error('Type IMPORT to confirm overwrite.')
      return
    }
    const confirmPhrase = requestProtectedDeleteConfirmation(Object.keys(counts))
    importMutation.mutate({ payload: parsedImport, confirmPhrase })
  }

  function handleClearDatabase() {
    if (clearConfirmText.trim().toUpperCase() !== 'CLEAR DATABASE') {
      toast.error('Type CLEAR DATABASE to confirm.')
      return
    }
    const confirmPhrase = requestProtectedDeleteConfirmation(Object.keys(counts))
    clearMutation.mutate({ confirmPhrase })
  }

  async function handleRecommendedReset() {
    setActionState({
      kind: 'clear',
      status: 'pending',
      title: 'Preparing recommended reset',
      message: 'Pausing autonomous scans and stopping any active run before clearing data.',
      startedAt: new Date().toISOString(),
    })
    try {
      await pauseScans('interface', profileScope)
      await stopScans('interface', profileScope)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to stop scans before reset.')
      setActionState({
        kind: 'clear',
        status: 'error',
        title: 'Recommended reset blocked',
        message: error instanceof Error ? error.message : 'Failed to stop scans before reset.',
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
      return
    }
    try {
      const confirmPhrase = requestProtectedDeleteConfirmation(recommendedReset?.components ?? [])
      clearGroupMutation.mutate({ groupId: 'recommended_engine_reset', confirmPhrase })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Protected deletion cancelled.'
      toast.error(message)
      setActionState({
        kind: 'clear',
        status: 'error',
        title: 'Recommended reset cancelled',
        message,
        startedAt: actionState.startedAt,
        finishedAt: new Date().toISOString(),
      })
    }
  }

  const status = (statusQuery.data ?? {}) as StorageStatusPayload
  const trashEntries = (trashQuery.data ?? []) as StorageTrashEntry[]
  const postgres = status.postgres
  const counts = postgres?.counts ?? {}
  const totalRecords = Object.values(counts).reduce((sum, value) => sum + Number(value ?? 0), 0)
  const clearGroups = status.clear_groups ?? []
  const recommendedReset = clearGroups.find((group) => group.group_id === 'recommended_engine_reset')

  function requestProtectedDeleteConfirmation(components: string[]) {
    const phrase = protectedConfirmPhraseForComponents(components)
    if (!phrase) return ''
    const typed = window.prompt(`This action archives protected data to trash for 30 days before deletion. Type exactly: ${phrase}`) ?? ''
    if (typed.trim().toUpperCase() !== phrase) {
      throw new Error(`Protected deletion cancelled. Type exactly: ${phrase}`)
    }
    return phrase
  }
  const componentRows = useMemo(
    () => Object.entries(counts)
      .map(([key, value]) => ({ key, value: Number(value ?? 0) }))
      .sort((left, right) => right.value - left.value || left.key.localeCompare(right.key)),
    [counts],
  )
  const filteredComponentRows = useMemo(() => {
    const query = componentSearch.trim().toLowerCase()
    if (!query) return componentRows
    return componentRows.filter((item) => item.key.toLowerCase().includes(query) || humanLabel(item.key).toLowerCase().includes(query))
  }, [componentRows, componentSearch])

  function toggleComponent(component: string) {
    setSelectedComponents((current) => (
      current.includes(component)
        ? current.filter((item) => item !== component)
        : [...current, component]
    ))
  }

  function handleClearOneComponent(component: string) {
    let confirmPhrase = ''
    try {
      confirmPhrase = requestProtectedDeleteConfirmation([component])
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Protected deletion cancelled.')
      return
    }
    clearGroupMutation.mutate({ components: [component], confirmPhrase }, {
      onSuccess: () => {
        setSelectedComponents((current) => current.filter((item) => item !== component))
      },
    })
  }

  function handleDeleteTrashForever(entry: StorageTrashEntry) {
    const trashId = String(entry.trash_id ?? '')
    if (!trashId) {
      toast.error('Trash entry is missing an id.')
      return
    }
    const typed = window.prompt('Type exactly: DELETE TRASH FOREVER') ?? ''
    if (typed.trim().toUpperCase() !== 'DELETE TRASH FOREVER') {
      toast.error('Permanent trash deletion cancelled.')
      return
    }
    deleteTrashMutation.mutate({ trashId, confirmPhrase: typed.trim().toUpperCase() })
  }

  function handleClearSelectedComponents() {
    if (!selectedComponents.length) {
      toast.error('Select at least one component to clear.')
      return
    }
    let confirmPhrase = ''
    try {
      confirmPhrase = requestProtectedDeleteConfirmation(selectedComponents)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Protected deletion cancelled.')
      return
    }
    clearGroupMutation.mutate({ components: selectedComponents, confirmPhrase }, {
      onSuccess: () => {
        setSelectedComponents([])
      },
    })
  }

  if (statusQuery.isLoading && !statusQuery.data) {
    return (
      <AnimatedRoute>
        <EmptyState message="Loading storage management..." />
      </AnimatedRoute>
    )
  }

  return (
    <AnimatedRoute>
      <div className="grid gap-4">
        <ProfileScopeBar
          options={profileScopeOptions}
          value={profileScope}
          onChange={(nextValue: ProfileScopeValue) => {
            const nextParams = new URLSearchParams(searchParams)
            if (nextValue === DEFAULT_PROFILE_SCOPE) {
              nextParams.delete('profile')
            } else {
              nextParams.set('profile', nextValue)
            }
            setSearchParams(nextParams)
          }}
        />
        <section className="rounded-[1.7rem] border border-stone-900/8 bg-white/84 px-5 py-5 shadow-[0_18px_40px_rgba(77,62,40,0.08)]">
          <div className="grid gap-3">
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-teal-800">Database Control Center</p>
            <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
              <div className="grid gap-2">
                <h1 className="text-3xl font-semibold tracking-[-0.06em] text-stone-950">PostgreSQL operational storage controls.</h1>
                <p className="max-w-4xl text-sm leading-6 text-stone-500">
                  Export, inspect, and clear operational storage with profile awareness. Scoped profile actions only affect that profile's owned runtime data.
                </p>
              </div>
              <button
                type="button"
                onClick={() => void statusQuery.refetch()}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
              >
                <RefreshCw className="h-4 w-4" strokeWidth={1.8} />
                Refresh
              </button>
            </div>
          </div>
        </section>

        {isScopedProfile ? (
          <section className="rounded-[1.3rem] border border-amber-900/12 bg-amber-50/90 p-4 text-amber-900">
            <p className="text-[0.72rem] uppercase tracking-[0.18em]">Scoped profile mode</p>
            <p className="mt-2 text-sm">You are viewing storage for <span className="font-semibold">{profileScope}</span>. Export and selective clear actions are profile-aware. Full seed, import, and clear-database actions are disabled here so you do not wipe other profiles.</p>
          </section>
        ) : null}

        <section className="grid gap-3 md:grid-cols-3">
          <div className={`rounded-[1.3rem] border p-4 ${backendTone(postgres?.healthy)}`}>
            <p className="text-[0.72rem] uppercase tracking-[0.18em]">Current DB State</p>
            <p className="mt-2 text-lg font-semibold">{postgres?.healthy ? 'Connected' : 'Unavailable'}</p>
            <p className="mt-2 text-sm">{postgres?.detail ?? 'No status detail.'}</p>
          </div>
          <div className="rounded-[1.3rem] border border-stone-900/8 bg-white p-4">
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Current Seed/Live State</p>
            <p className="mt-2 text-lg font-semibold text-stone-950">{status.state?.label ?? 'Unknown state'}</p>
            <p className="mt-2 text-sm text-stone-500">{status.state?.note ?? 'No storage state detail.'}</p>
          </div>
          <div className={`rounded-[1.3rem] border p-4 ${actionTone(actionState.status)}`}>
            <p className="text-[0.72rem] uppercase tracking-[0.18em]">Current Action Status</p>
            <p className="mt-2 text-lg font-semibold">{actionState.title}</p>
            <p className="mt-2 text-sm">{actionState.message}</p>
            <p className="mt-2 text-xs opacity-75">Started {formatTime(actionState.startedAt)} · Finished {formatTime(actionState.finishedAt)}</p>
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {componentRows.map(({ key, value }) => (
            <div key={key} className="rounded-[1.25rem] border border-stone-900/8 bg-white p-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
              <p className="text-[0.68rem] uppercase tracking-[0.16em] text-stone-500">{humanLabel(key)}</p>
              <p className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-stone-950">{compactNumber(value)}</p>
            </div>
          ))}
          <div className="rounded-[1.25rem] border border-stone-900/8 bg-stone-950/[0.03] p-4 shadow-[0_12px_24px_rgba(71,53,29,0.05)]">
            <p className="text-[0.68rem] uppercase tracking-[0.16em] text-stone-500">Total Records</p>
            <p className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-stone-950">{compactNumber(totalRecords)}</p>
            <p className="mt-2 text-sm text-stone-500">Updated {formatTime(status.generated_at)}</p>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="grid gap-4">
            <div className="rounded-[1.4rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_16px_34px_rgba(77,62,40,0.08)]">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-stone-950">Export</p>
                  <p className="text-sm text-stone-500">Download or copy the current PostgreSQL operational state.</p>
                </div>
                <HardDriveDownload className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => exportMutation.mutate()}
                  disabled={exportMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-full bg-stone-950 px-4 py-2.5 text-sm font-semibold text-stone-50 transition hover:bg-stone-900 disabled:opacity-60"
                >
                  <Download className="h-4 w-4" strokeWidth={1.8} />
                  Download JSON
                </button>
                <button
                  type="button"
                  onClick={handleCopyExport}
                  disabled={exportMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                >
                  <Copy className="h-4 w-4" strokeWidth={1.8} />
                  Copy JSON
                </button>
              </div>
            </div>

            <div className="rounded-[1.4rem] border border-teal-900/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(230,247,245,0.8))] p-4 shadow-[0_16px_34px_rgba(77,62,40,0.08)]">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-stone-950">Seed Controls</p>
                  <p className="text-sm text-stone-500">Compact seed, fuller seed, or reset back to live-only state.</p>
                </div>
                <Database className="h-5 w-5 text-teal-800" strokeWidth={1.8} />
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                {([
                  ['seed', 'Seed Data'],
                  ['all', 'Full Seed'],
                  ['real', 'Use Real Data'],
                ] as [StorageSeedMode, string][]).map(([mode, label]) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => {
                      try {
                        const confirmPhrase = requestProtectedDeleteConfirmation(Object.keys(counts))
                        seedMutation.mutate({ mode, confirmPhrase })
                      } catch (error) {
                        toast.error(error instanceof Error ? error.message : 'Protected deletion cancelled.')
                      }
                    }}
                    disabled={seedMutation.isPending || isScopedProfile}
                    className="inline-flex items-center justify-center gap-2 rounded-[1.15rem] border border-stone-900/8 bg-white px-4 py-3 text-sm font-semibold text-stone-900 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                  >
                    {seedMutation.isPending ? 'Working…' : label}
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-[1.4rem] border border-rose-900/12 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(254,235,235,0.92))] p-4 shadow-[0_16px_34px_rgba(77,62,40,0.08)]">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-stone-950">Danger Zone</p>
                  <p className="text-sm text-stone-500">
                    Wipe the operational PostgreSQL database, including runtime settings. This cannot be undone.
                  </p>
                </div>
                <ShieldAlert className="h-5 w-5 text-rose-700" strokeWidth={1.8} />
              </div>
              <div className="mt-4 flex flex-col gap-3">
                <input
                  value={clearConfirmText}
                  onChange={(event) => setClearConfirmText(event.target.value)}
                  placeholder="Type CLEAR DATABASE to confirm"
                  className="h-11 rounded-full border border-rose-900/12 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-rose-900/20 focus:ring-4 focus:ring-rose-900/6"
                />
                <button
                  type="button"
                  onClick={handleClearDatabase}
                  disabled={clearMutation.isPending || isScopedProfile}
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-rose-800 px-4 py-2.5 text-sm font-semibold text-stone-50 transition hover:bg-rose-900 disabled:opacity-60"
                >
                  <ShieldAlert className="h-4 w-4" strokeWidth={1.8} />
                  {clearMutation.isPending ? 'Clearing…' : 'Clear Database'}
                </button>
              </div>
            </div>

            <div className="rounded-[1.4rem] border border-amber-900/12 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(255,246,230,0.92))] p-4 shadow-[0_16px_34px_rgba(77,62,40,0.08)]">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-stone-950">Selective Clear</p>
                  <p className="text-sm text-stone-500">Clear only the parts you want to reset. You can now search for a component, select it, and delete just that one.</p>
                </div>
                <ShieldAlert className="h-5 w-5 text-amber-700" strokeWidth={1.8} />
              </div>
              {recommendedReset ? (
                <div className="mt-4 rounded-[1.05rem] border border-amber-900/10 bg-white/90 p-4">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="grid gap-2">
                      <p className="text-sm font-semibold text-stone-950">{recommendedReset.label ?? 'Recommended Engine Reset'}</p>
                      <p className="text-sm text-stone-500">{recommendedReset.description}</p>
                      <p className="text-xs text-stone-500">{(recommendedReset.components ?? []).join(', ')}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleRecommendedReset()}
                      disabled={clearGroupMutation.isPending}
                      className="inline-flex items-center justify-center gap-2 rounded-full bg-amber-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-800 disabled:opacity-60"
                    >
                      {clearGroupMutation.isPending ? 'Clearing…' : 'Run Recommended Reset'}
                    </button>
                  </div>
                </div>
              ) : null}

              <div className="mt-4 rounded-[1.05rem] border border-stone-900/8 bg-white/90 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-stone-950">Clear individual components</p>
                    <p className="text-sm text-stone-500">Example: search <span className="font-semibold text-stone-700">profit</span>, then clear just that storage component if it exists.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={handleClearSelectedComponents}
                      disabled={clearGroupMutation.isPending || !selectedComponents.length}
                      className="inline-flex items-center justify-center gap-2 rounded-full bg-amber-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-800 disabled:opacity-60"
                    >
                      {clearGroupMutation.isPending ? 'Clearing…' : `Clear selected${selectedComponents.length ? ` (${selectedComponents.length})` : ''}`}
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedComponents([])}
                      disabled={!selectedComponents.length}
                      className="inline-flex items-center justify-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-900 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                    >
                      Clear selection
                    </button>
                  </div>
                </div>
                <input
                  value={componentSearch}
                  onChange={(event) => setComponentSearch(event.target.value)}
                  placeholder="Search components, e.g. profit, signals, orders"
                  className="mt-4 h-11 w-full rounded-full border border-stone-900/8 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-amber-900/20 focus:ring-4 focus:ring-amber-900/6"
                />
                <div className="mt-4 grid gap-3 max-h-[24rem] overflow-auto pr-1">
                  {filteredComponentRows.length ? filteredComponentRows.map(({ key, value }) => {
                    const selected = selectedComponents.includes(key)
                    return (
                      <div key={key} className={`rounded-[1rem] border px-4 py-3 ${selected ? 'border-amber-900/20 bg-amber-50/70' : 'border-stone-900/8 bg-stone-50/70'}`}>
                        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                          <label className="flex items-center gap-3 text-sm text-stone-700">
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => toggleComponent(key)}
                              className="h-4 w-4 rounded border-stone-300 text-amber-700 focus:ring-amber-700"
                            />
                            <span>
                              <span className="font-semibold text-stone-950">{humanLabel(key)}</span>
                              <span className="ml-2 text-stone-500">({compactNumber(value)})</span>
                            </span>
                          </label>
                          <button
                            type="button"
                            onClick={() => handleClearOneComponent(key)}
                            disabled={clearGroupMutation.isPending}
                            className="inline-flex items-center justify-center gap-2 rounded-full border border-rose-900/10 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100 disabled:opacity-60"
                          >
                            Delete just this
                          </button>
                        </div>
                        <p className="mt-2 text-xs text-stone-500">Component key: <span className="font-mono">{key}</span></p>
                      </div>
                    )
                  }) : (
                    <EmptyState message="No storage components matched that search." />
                  )}
                </div>
              </div>

              <div className="mt-4 grid gap-3">
                {clearGroups
                  .filter((group) => group.group_id && group.group_id !== 'recommended_engine_reset')
                  .map((group) => (
                    <div key={group.group_id} className="rounded-[1.05rem] border border-stone-900/8 bg-white/90 p-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div className="grid gap-2">
                          <p className="text-sm font-semibold text-stone-950">{group.label ?? group.group_id}</p>
                          <p className="text-sm text-stone-500">{group.description}</p>
                          <p className="text-xs text-stone-500">{(group.components ?? []).join(', ')}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            try {
                              const confirmPhrase = requestProtectedDeleteConfirmation(group.components ?? [])
                              clearGroupMutation.mutate({ groupId: group.group_id, confirmPhrase })
                            } catch (error) {
                              toast.error(error instanceof Error ? error.message : 'Protected deletion cancelled.')
                            }
                          }}
                          disabled={clearGroupMutation.isPending}
                          className="inline-flex items-center justify-center gap-2 rounded-full border border-stone-900/8 bg-white px-4 py-2.5 text-sm font-semibold text-stone-900 transition hover:bg-stone-950/[0.03] disabled:opacity-60"
                        >
                          Clear
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </div>

          <div className="rounded-[1.4rem] border border-rose-900/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(251,231,231,0.88))] p-4 shadow-[0_16px_34px_rgba(77,62,40,0.08)]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-stone-950">Import / Restore</p>
                <p className="text-sm text-stone-500">Paste exported JSON, preview the counts, then type <span className="font-semibold text-rose-800">IMPORT</span> to overwrite operational state.</p>
              </div>
              <ShieldAlert className="h-5 w-5 text-rose-700" strokeWidth={1.8} />
            </div>
            <textarea
              value={importText}
              onChange={(event) => setImportText(event.target.value)}
              spellCheck={false}
              placeholder='Paste exported JSON here'
              disabled={isScopedProfile}
              className="mt-4 h-48 w-full rounded-[1.1rem] border border-stone-900/8 bg-white px-4 py-3 font-mono text-xs text-stone-900 outline-none transition focus:border-rose-900/20 focus:ring-4 focus:ring-rose-900/6"
            />
            <div className="mt-3 rounded-[1.05rem] border border-stone-900/8 bg-white/90 px-4 py-3">
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-stone-500">Preview</p>
              <p className="mt-2 text-sm text-stone-600">
                {parsedImport
                  ? importPreviewQuery.isLoading
                    ? 'Previewing import payload…'
                    : importPreviewQuery.data
                      ? summarizeCounts(importPreviewQuery.data.counts)
                      : 'Preview unavailable.'
                  : 'Paste valid JSON to preview imported record counts.'}
              </p>
            </div>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row">
              <input
                value={confirmText}
                onChange={(event) => setConfirmText(event.target.value)}
                placeholder="Type IMPORT to confirm"
                className="h-11 flex-1 rounded-full border border-stone-900/8 bg-white px-4 text-sm text-stone-900 outline-none transition focus:border-rose-900/20 focus:ring-4 focus:ring-rose-900/6"
              />
              <button
                type="button"
                onClick={handleImport}
                disabled={importMutation.isPending || !parsedImport || isScopedProfile}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-rose-800 px-4 py-2.5 text-sm font-semibold text-stone-50 transition hover:bg-rose-900 disabled:opacity-60"
              >
                <HardDriveUpload className="h-4 w-4" strokeWidth={1.8} />
                {importMutation.isPending ? 'Importing…' : 'Import JSON'}
              </button>
            </div>
          </div>
        </section>

        <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_16px_34px_rgba(77,62,40,0.08)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-stone-950">Trash Bin</p>
              <p className="text-sm text-stone-500">Archived deletions are retained for 30 days before expiry. You can permanently remove a trash bundle here.</p>
            </div>
            <p className="text-xs uppercase tracking-[0.18em] text-stone-500">{compactNumber(trashEntries.length)} bundles</p>
          </div>
          <div className="mt-4 grid gap-3">
            {trashEntries.length ? trashEntries.map((entry) => (
              <div key={String(entry.trash_id)} className="rounded-[1.05rem] border border-stone-900/8 bg-stone-50/70 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="grid gap-1">
                    <p className="text-sm font-semibold text-stone-950">{entry.operation ?? 'delete'} · {entry.trash_id}</p>
                    <p className="text-xs text-stone-500">Archived {formatTime(entry.archived_at)} · Expires {formatTime(entry.expires_at)}{entry.profile_id ? ` · Profile ${entry.profile_id}` : ''}</p>
                    <p className="text-sm text-stone-600">{(entry.components ?? []).join(', ') || 'No components recorded.'}</p>
                    <p className="text-xs text-stone-500">{summarizeCounts(entry.counts)}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDeleteTrashForever(entry)}
                    disabled={deleteTrashMutation.isPending}
                    className="inline-flex items-center justify-center gap-2 rounded-full border border-rose-900/10 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-900 transition hover:bg-rose-100 disabled:opacity-60"
                  >
                    Delete forever
                  </button>
                </div>
              </div>
            )) : (
              <EmptyState message="Trash bin is empty." />
            )}
          </div>
        </section>

        {parsedImport ? (
          <section className="rounded-[1.4rem] border border-stone-900/8 bg-white/82 p-4 shadow-[0_16px_34px_rgba(77,62,40,0.08)]">
            <div className="mb-3 flex items-center gap-2">
              <RotateCcw className="h-4 w-4 text-teal-800" strokeWidth={1.8} />
              <p className="text-sm font-semibold text-stone-950">Import Payload Preview</p>
            </div>
            <JsonViewer json={parsedImport} />
          </section>
        ) : null}
      </div>
    </AnimatedRoute>
  )
}
