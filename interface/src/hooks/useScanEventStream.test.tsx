import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildScanEventsSseUrl, shouldAcceptScanEvent, useScanEventStream } from './useScanEventStream'
import type { ScanEvent } from '../lib/types'

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

function scanEvent(overrides: Partial<ScanEvent> = {}): ScanEvent {
  return {
    type: 'SCAN_PROGRESS',
    timestamp: '2026-04-27T00:00:00Z',
    profile_id: 'paper-main',
    run_id: 'scan-1',
    ...overrides,
  }
}

describe('useScanEventStream', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    MockEventSource.instances = []
  })

  it('builds an SSE URL with active profile_id', () => {
    expect(buildScanEventsSseUrl('paper-main')).toContain('/api/v3/scans/events-sse?profile_id=paper-main')
  })

  it('builds an SSE URL with run_id when provided', () => {
    const url = buildScanEventsSseUrl('paper-main', 'scan-123')
    expect(url).toContain('profile_id=paper-main')
    expect(url).toContain('run_id=scan-123')
  })

  it('closes and replaces the connection on profile change', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    const { rerender } = renderHook(({ profileScope }) => useScanEventStream({ profileScope, runId: 'scan-1' }), {
      initialProps: { profileScope: 'paper-main' },
    })

    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('profile_id=paper-main')

    rerender({ profileScope: 'paper-alt' })

    expect(MockEventSource.instances[0].close).toHaveBeenCalledTimes(1)
    expect(MockEventSource.instances).toHaveLength(2)
    expect(MockEventSource.instances[1].url).toContain('profile_id=paper-alt')
  })

  it('ignores events from another profile', () => {
    expect(shouldAcceptScanEvent(scanEvent({ profile_id: 'paper-alt' }), 'paper-main', null)).toBe(false)
  })

  it('ignores events from another run when run_id is active', () => {
    expect(shouldAcceptScanEvent(scanEvent({ run_id: 'scan-2' }), 'paper-main', 'scan-1')).toBe(false)
  })

  it('keeps latest event for matching profile and run only', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    const { result } = renderHook(() => useScanEventStream({ profileScope: 'paper-main', runId: 'scan-1' }))
    const source = MockEventSource.instances[0]

    act(() => {
      source.emit(scanEvent({ profile_id: 'paper-alt', run_id: 'scan-1', stage: 'WRONG_PROFILE' }))
      source.emit(scanEvent({ profile_id: 'paper-main', run_id: 'scan-2', stage: 'WRONG_RUN' }))
      source.emit(scanEvent({ profile_id: 'paper-main', run_id: 'scan-1', stage: 'ANALYSIS' }))
    })

    expect(result.current.latestEvent?.stage).toBe('ANALYSIS')
    expect(result.current.events).toHaveLength(1)
  })

  it('does not throw when EventSource is unavailable', () => {
    vi.stubGlobal('EventSource', undefined)
    const { result } = renderHook(() => useScanEventStream({ profileScope: 'paper-main' }))

    expect(result.current.connectionState).toBe('error')
    expect(result.current.latestEvent).toBeNull()
  })
})
