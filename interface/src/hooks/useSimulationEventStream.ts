import { useEffect, useMemo, useState } from 'react'

import { apiRoutes } from '../lib/apiRoutes'
import type { SimulationEvent } from '../lib/types'

export type SimulationEventConnectionState = 'disabled' | 'connecting' | 'open' | 'closed' | 'error'

export function buildSimulationEventsSseUrl(runId: number) {
  const path = apiRoutes.simulationEventsSse(runId)
  if (typeof window === 'undefined') return path
  const host = window.location.port === '5173'
    ? `${window.location.hostname}:8000`
    : window.location.host
  return `${window.location.protocol}//${host}${path}`
}

// Backwards-compatible export for older tests/imports. The stream now uses SSE.
export const buildSimulationEventsWebSocketUrl = buildSimulationEventsSseUrl

export function shouldAcceptSimulationEvent(event: SimulationEvent, runId: number) {
  const eventRunId = Number(event.run_id ?? event.run?.id ?? runId)
  return Number.isFinite(eventRunId) && eventRunId === runId
}

export function useSimulationEventStream({
  runId,
  enabled = true,
}: {
  runId?: number | null
  enabled?: boolean
}) {
  const resolvedRunId = typeof runId === 'number' && Number.isFinite(runId) ? runId : null
  const [connectionState, setConnectionState] = useState<SimulationEventConnectionState>(enabled && resolvedRunId != null ? 'connecting' : 'disabled')
  const [latestEvent, setLatestEvent] = useState<SimulationEvent | null>(null)
  const [events, setEvents] = useState<SimulationEvent[]>([])

  const url = useMemo(() => resolvedRunId == null ? '' : buildSimulationEventsSseUrl(resolvedRunId), [resolvedRunId])

  useEffect(() => {
    setLatestEvent(null)
    setEvents([])
    if (!enabled || resolvedRunId == null || typeof EventSource === 'undefined') {
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
        const payload = JSON.parse(String(message.data)) as SimulationEvent
        if (!payload?.type || !shouldAcceptSimulationEvent(payload, resolvedRunId)) return
        if (String(payload.type).toLowerCase() === 'heartbeat') return
        setLatestEvent(payload)
        setEvents((current) => [payload, ...current].slice(0, 75))
      } catch {
        // Ignore malformed SSE messages. HTTP query state remains authoritative.
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
  }, [enabled, resolvedRunId, url])

  return { runId: resolvedRunId, url, connectionState, latestEvent, events }
}
