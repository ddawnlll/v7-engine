import { useEffect, useMemo, useState } from 'react'

import { apiRoutes } from '../lib/apiRoutes'
import { profileScopeToApiProfileId } from '../lib/profileScope'
import type { ScanEvent } from '../lib/types'

export type ScanEventConnectionState = 'disabled' | 'connecting' | 'open' | 'closed' | 'error'

export function buildScanEventsSseUrl(profileId: string, runId?: string | null) {
  const params = new URLSearchParams({ profile_id: profileId })
  const resolvedRunId = String(runId ?? '').trim()
  if (resolvedRunId) params.set('run_id', resolvedRunId)
  const path = `${apiRoutes.scanEventsSse()}?${params.toString()}`
  if (typeof window === 'undefined') return path
  const host = window.location.port === '5173'
    ? `${window.location.hostname}:8000`
    : window.location.host
  return `${window.location.protocol}//${host}${path}`
}

// Backwards-compatible export for older tests/imports. The stream now uses SSE.
export const buildScanEventsWebSocketUrl = buildScanEventsSseUrl

export function shouldAcceptScanEvent(event: ScanEvent, profileId: string, runId?: string | null) {
  if (String(event.profile_id ?? '') !== profileId) return false
  const resolvedRunId = String(runId ?? '').trim()
  if (resolvedRunId && String(event.run_id ?? '') !== resolvedRunId) return false
  return true
}

export function useScanEventStream({
  profileScope,
  runId,
  enabled = true,
}: {
  profileScope?: string
  runId?: string | null
  enabled?: boolean
}) {
  const profileId = profileScopeToApiProfileId(profileScope) || 'paper-main'
  const resolvedRunId = String(runId ?? '').trim() || null
  const [connectionState, setConnectionState] = useState<ScanEventConnectionState>(enabled ? 'connecting' : 'disabled')
  const [latestEvent, setLatestEvent] = useState<ScanEvent | null>(null)
  const [events, setEvents] = useState<ScanEvent[]>([])

  const url = useMemo(() => buildScanEventsSseUrl(profileId, resolvedRunId), [profileId, resolvedRunId])

  useEffect(() => {
    setLatestEvent(null)
    setEvents([])
    if (!enabled || typeof EventSource === 'undefined') {
      setConnectionState(enabled ? 'error' : 'disabled')
      return
    }

    let closed = false
    setConnectionState('connecting')
    const source = new EventSource(url)

    source.onopen = () => {
      if (!closed) setConnectionState('open')
    }
    source.onmessage = (message) => {
      if (closed) return
      try {
        const payload = JSON.parse(String(message.data)) as ScanEvent
        if (!payload?.type || !shouldAcceptScanEvent(payload, profileId, resolvedRunId)) return
        if (payload.type === 'HEARTBEAT') return
        setLatestEvent(payload)
        setEvents((current) => [payload, ...current].slice(0, 50))
      } catch {
        // Ignore malformed SSE messages; HTTP polling remains authoritative.
      }
    }
    source.onerror = () => {
      if (!closed) setConnectionState('error')
      // EventSource reconnects automatically; keep polling fallback active while errored.
    }

    return () => {
      closed = true
      source.close()
      setConnectionState('closed')
    }
  }, [enabled, profileId, resolvedRunId, url])

  return { profileId, runId: resolvedRunId, url, connectionState, latestEvent, events }
}
