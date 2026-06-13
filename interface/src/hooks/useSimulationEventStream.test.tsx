import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildSimulationEventsSseUrl, shouldAcceptSimulationEvent, useSimulationEventStream } from './useSimulationEventStream'

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }
}

describe('simulation event stream helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    MockEventSource.instances = []
  })

  it('builds the simulation SSE URL', () => {
    expect(buildSimulationEventsSseUrl(42)).toBe('http://localhost:3000/api/v3/simulations/42/events-sse')
  })

  it('bypasses the Vite dev proxy for simulation SSE', () => {
    vi.stubGlobal('location', new URL('http://localhost:5173/system/simulations'))
    expect(buildSimulationEventsSseUrl(42)).toBe('http://localhost:8000/api/v3/simulations/42/events-sse')
  })

  it('accepts only events for the selected run', () => {
    expect(shouldAcceptSimulationEvent({ type: 'progress', run_id: 42 }, 42)).toBe(true)
    expect(shouldAcceptSimulationEvent({ type: 'progress', run: { id: 42 } }, 42)).toBe(true)
    expect(shouldAcceptSimulationEvent({ type: 'progress', run_id: 41 }, 42)).toBe(false)
  })

  it('keeps latest event from EventSource and ignores heartbeats', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    const { result } = renderHook(() => useSimulationEventStream({ runId: 42 }))
    const source = MockEventSource.instances[0]

    act(() => {
      source.onopen?.()
      source.emit({ type: 'heartbeat', run_id: 42 })
      source.emit({ type: 'progress', run_id: 41, metrics: { progress_pct: 10 } })
      source.emit({ type: 'progress', run_id: 42, metrics: { progress_pct: 50 } })
    })

    expect(result.current.connectionState).toBe('open')
    expect(result.current.latestEvent?.type).toBe('progress')
    expect(result.current.events).toHaveLength(1)
  })
})
