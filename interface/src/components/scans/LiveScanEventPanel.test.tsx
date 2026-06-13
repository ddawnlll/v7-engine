import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'

import { LiveScanEventPanel } from './LiveScanEventPanel'
import { renderWithRouter } from '../../test/renderWithRouter'
import type { ScanEvent } from '../../lib/types'

function event(overrides: Partial<ScanEvent> = {}): ScanEvent {
  return {
    type: 'SCAN_PROGRESS',
    timestamp: '2026-04-27T00:00:00Z',
    profile_id: 'paper-main',
    run_id: 'scan-1',
    stage: 'ANALYSIS',
    total_tasks: 10,
    completed_tasks: 4,
    percent_complete: 40,
    ...overrides,
  }
}

describe('LiveScanEventPanel', () => {
  it('renders latest event, stage, and progress', () => {
    renderWithRouter(
      <LiveScanEventPanel
        latestEvent={event({ symbol: 'BTCUSDT', interval: '15m', mode: 'SWING' })}
        events={[event({ symbol: 'BTCUSDT', interval: '15m', mode: 'SWING' })]}
        connectionState="open"
        profileId="paper-main"
        runId="scan-1"
      />,
    )

    expect(screen.getByText('Live scan stream')).toBeInTheDocument()
    expect(screen.getByText('live')).toBeInTheDocument()
    expect(screen.getAllByText('ANALYSIS')).toHaveLength(2)
    expect(screen.getByText('4/10 tasks')).toBeInTheDocument()
    expect(screen.getByText('BTCUSDT · 15m · SWING')).toBeInTheDocument()
  })

  it('renders inference failure/degraded messages', () => {
    const failure = event({
      type: 'INFERENCE_JOB_FAILED',
      stage: 'FAILED',
      message: 'engine exploded',
      reason_code: 'INFERENCE_FAILED',
      job_id: 'infjob-1',
    })
    renderWithRouter(
      <LiveScanEventPanel
        latestEvent={failure}
        events={[failure]}
        connectionState="open"
        profileId="paper-main"
        runId="scan-1"
      />,
    )

    expect(screen.getAllByText('INFERENCE JOB FAILED').length).toBeGreaterThan(0)
    expect(screen.getAllByText('engine exploded').length).toBeGreaterThan(0)
    expect(screen.getAllByText('FAILED').length).toBeGreaterThan(0)
  })

  it('renders fallback messaging when the websocket is unavailable', () => {
    renderWithRouter(
      <LiveScanEventPanel
        latestEvent={null}
        events={[]}
        connectionState="error"
        profileId="paper-main"
        runId={null}
      />,
    )

    expect(screen.getByText('degraded')).toBeInTheDocument()
    expect(screen.getByText(/Live stream unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/Polling remains the source of truth/i)).toBeInTheDocument()
  })
})
