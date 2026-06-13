import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

import { SimulationsRoute } from './SimulationsRoute'
import { renderWithRouter } from '../test/renderWithRouter'
import {
  createSimulation,
  fetchSimulationDecisionTraces,
  fetchSimulationExport,
  fetchSimulationWhatIf,
} from '../lib/api'

vi.mock('framer-motion', async () => {
  const React = await vi.importActual<typeof import('react')>('react')
  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: new Proxy(
      {},
      {
        get: (_target, tag: string) =>
          React.forwardRef<HTMLElement, Record<string, unknown>>(
            ({ children, layout: _layout, initial: _initial, animate: _animate, exit: _exit, transition: _transition, ...props }, ref) =>
              React.createElement(tag, { ...props, ref }, children as React.ReactNode),
          ),
      },
    ),
  }
})

vi.mock('../hooks/useSimulationEventStream', () => ({
  useSimulationEventStream: () => ({
    runId: 7,
    url: '/api/v3/simulations/7/events-sse',
    connectionState: 'disabled',
    latestEvent: null,
    events: [],
  }),
}))

vi.mock('../lib/export', () => ({
  copyToClipboard: vi.fn(async () => undefined),
  downloadFile: vi.fn(),
  exportAsCSV: vi.fn(() => 'csv'),
  exportFilename: vi.fn((name: string, ext: string) => `${name}.${ext}`),
}))

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  const run = {
    id: 7,
    name: 'Old run',
    status: 'COMPLETED',
    parameters: {
      period_start: '2026-01-01',
      period_end: '2026-01-02',
      symbols: ['BTCUSDT'],
      intervals: ['1h'],
      modes: ['SCALP'],
      capital: 10000,
      execution_settings: { require_htf_context: true },
    },
    metrics: {
      progress_pct: 100,
      trade_count: 0,
      reproducibility: {
        request_payload_hash: 'abc123',
        execution_settings_hash: 'def456',
        contract_version: 'analysis_request_vnext',
      },
    },
  }
  return {
    ...actual,
    fetchSymbols: vi.fn(async () => ({ symbols: ['BTCUSDT', 'ETHUSDT'] })),
    fetchRuntimeSettingsForScope: vi.fn(async () => ({
      AUTONOMOUS_SYMBOLS: 'BTCUSDT,ETHUSDT',
      AUTONOMOUS_INTERVALS: '1h,4h',
      AUTONOMOUS_MODES: 'SCALP,SWING',
    })),
    fetchSimulations: vi.fn(async () => ({ ok: true, runs: [run] })),
    fetchSimulationRun: vi.fn(async () => ({ ok: true, run, results: [] })),
    fetchSimulationDiagnostics: vi.fn(async () => ({
      ok: true,
      run_id: 7,
      has_traces: false,
      trace_coverage: { has_traces: false, trace_count: 0, coverage_status: 'missing' },
      decision_distribution: { neutral: 10, low_confidence: 5 },
      confidence_summary: { threshold: 50, below_threshold_count: 5 },
      confidence_histogram: [{ bucket_start: 50, bucket_end: 60, count: 0, threshold_in_bucket: true }],
      top_blockers: [
        { reason: 'low_confidence', count: 5, percentage: 50, affected_symbols: ['BTCUSDT'] },
        { reason: 'analysis_fallback:v4_deterministic', count: 3, percentage: 30, affected_symbols: ['BTCUSDT'] },
        { reason: 'engine_filtered', count: 2, percentage: 20, affected_symbols: ['ETHUSDT'] },
      ],
      per_symbol_summary: [{ symbol: 'BTCUSDT', decision_count: 8, executed_trade_count: 0, total_pnl: 0 }],
      per_mode_summary: [{ mode: 'SCALP', decision_count: 8, executed_trade_count: 0, total_pnl: 0 }],
      directional_but_filtered: { directional_total_filtered: 2 },
      health: { status: 'UNKNOWN', score: null, reasons: ['no_decision_traces'], recommended_actions: ['Rerun with diagnostics.'] },
    })),
    fetchSimulationDecisionTraces: vi.fn(async (_runId, params) => ({
      ok: true,
      run_id: 7,
      items: [{ trace_id: `tr-${params?.cursor ?? 1}`, symbol: 'BTCUSDT', interval: '1h', mode: 'SCALP', timestamp: '2026-01-01T00:00:00Z', direction: 'BUY', confidence: 80, signal_status: 'SIGNAL', fallback_used: false, summary: 'buy setup' }],
      count: 1,
      next_cursor: params?.cursor ? null : 9,
      has_more: !params?.cursor,
    })),
    fetchSimulationWhatIf: vi.fn(async () => ({
      ok: true,
      run_id: 7,
      available: true,
      estimate_type: 'approximate',
      current_min_confidence: 50,
      hypothetical_min_confidence: 25,
      current_actionable_count: 1,
      hypothetical_actionable_count: 2,
    })),
    fetchSimulationParityReport: vi.fn(async () => ({ ok: true, run_id: 7, available: false, reason: 'no_comparable_scan_data', compared_decision_count: 0, missing_scan_context_count: 0, missing_sim_context_count: 0, mismatches: [] })),
    fetchSimulationExport: vi.fn(async () => ({ ok: true, items: [] })),
    createSimulation: vi.fn(async () => ({ ok: true, run: { id: 8 } })),
    stopSimulation: vi.fn(async () => ({ ok: true })),
    forceStopSimulation: vi.fn(async () => ({ ok: true })),
  }
})

describe('SimulationsRoute', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() })
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders the normalized simulation shell, intelligence cards, SSE panel, and diagnostics', async () => {
    renderWithRouter(<SimulationsRoute />, { route: '/system/simulations' })

    expect(await screen.findByRole('heading', { name: /Backtesting & Simulations/i })).toBeInTheDocument()
    expect(await screen.findByTestId('simulation-health-card')).toBeInTheDocument()
    expect(screen.getByTestId('live-simulation-event-panel')).toBeInTheDocument()
    expect(screen.getByTestId('simulation-intelligence-summary')).toBeInTheDocument()
    expect(screen.getByText('abc123')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /Diagnostics/i }))
    expect(await screen.findByTestId('simulation-diagnostics-panel')).toBeInTheDocument()
    expect(screen.getByText(/Top blockers/i)).toBeInTheDocument()
    expect(screen.getByText(/Trade creation funnel/i)).toBeInTheDocument()
  })

  it('drives trace filters, pagination, what-if, exports, parity, and rerun actions', async () => {
    renderWithRouter(<SimulationsRoute />, { route: '/system/simulations' })
    await waitFor(() => expect(screen.getAllByText(/Old run/i).length).toBeGreaterThan(0))

    fireEvent.click(screen.getByRole('tab', { name: /Decision trace/i }))
    expect(await screen.findByText('buy setup')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Low confidence/i }))
    expect(screen.getByLabelText('Trace reason filter')).toHaveValue('low_confidence')
    fireEvent.click(await screen.findByRole('button', { name: /Load next page/i }))
    await waitFor(() => expect(fetchSimulationDecisionTraces).toHaveBeenCalledWith(7, expect.objectContaining({ cursor: 9 })))

    fireEvent.click(screen.getByRole('tab', { name: /What-If/i }))
    expect(await screen.findByText(/estimate_type=approximate/i)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Min confidence/i), { target: { value: '25' } })
    await waitFor(() => expect(fetchSimulationWhatIf).toHaveBeenCalledWith(7, expect.objectContaining({ min_confidence: 25 })))

    fireEvent.click(screen.getByRole('tab', { name: /Exports/i }))
    fireEvent.click(await screen.findByRole('button', { name: /Download export/i }))
    await waitFor(() => expect(fetchSimulationExport).toHaveBeenCalledWith(7, expect.objectContaining({ target: 'decision_traces', format: 'json' })))

    fireEvent.click(screen.getByRole('tab', { name: /Parity/i }))
    expect(await screen.findByText(/No comparable scan data/i)).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /Rerun with diagnostics/i })[0])
    await waitFor(() => expect(createSimulation).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Diagnostic rerun of #7',
      execution_settings: expect.objectContaining({ record_htf_availability: true, require_htf_context: true }),
    }), expect.anything()))
  })
})
