import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { OperateControlPageRoute } from './OperateControlPageRoute'
import { renderWithRouter } from '../test/renderWithRouter'
import * as api from '../lib/api'

vi.mock('../lib/api', () => ({
  fetchRuntimeProfiles: vi.fn(async () => ({
    items: [
      { profile_id: 'paper-main', execution_mode: 'PAPER', venue: 'INTERNAL_PAPER', read_only: false },
      { profile_id: 'binance-usdm-main', execution_mode: 'LIVE', venue: 'BINANCE_USDM', read_only: true },
    ],
  })),
  fetchOperateChampion: vi.fn(async () => ({
    champion: {
      model_artifact_version: 'champ-1',
      engine_name: 'v4',
      engine_version: '1.0.0',
    },
    available_engines: [{ engine_name: 'v4', engine_version: '1.0.0' }],
  })),
  fetchOperateRuntimeStatus: vi.fn(async () => ({
    active_engine: 'v4',
    champion_version: 'champ-1',
    fallback_active: false,
    runtime_state: 'ready',
    active_engine_version: '1.0.0',
    healthy: true,
    consecutive_failures: 0,
    shadow_status: { active: false },
  })),
  fetchOperateModels: vi.fn(async () => ({
    items: [
      {
        model_artifact_version: 'champ-1',
        engine_name: 'v4',
        engine_version: '1.0.0',
        role: 'champion',
        metrics: { expectancy_r: 1.2, win_rate: 0.61, sample_size: 12 },
        promotion_readiness: { active_eligible: true, blocking_reasons: [] },
        comparison_to_champion: { expectancy_r_delta: 0 },
        training_timestamp_utc: '2026-04-23T10:00:00Z',
      },
    ],
  })),
  fetchEngineHealthForScope: vi.fn(async () => ({
    runtime_status: 'ready',
    runtime_readiness: { runtime_state: 'ready' },
    last_scan_completed_at_utc: '2026-04-23T12:00:00Z',
    next_scan_at_utc: '2026-04-23T12:05:00Z',
  })),
  fetchPaperBalanceForScope: vi.fn(async () => ({
    profile_id: 'paper-main',
    resolved_config_hash: 'hash-123',
    balance: 1500,
    account: { account_id: 'paper-main:default' },
  })),
  fetchRuntimeSettingsForScope: vi.fn(async () => ({ AUTONOMOUS_ENABLED: 'true' })),
  fetchOperatorAlertsForScope: vi.fn(async () => ({ items: [{ alert_id: 'a-1' }] })),
  fetchRuntimeProfileReadOnlyExposure: vi.fn(async () => ({
    profile: {
      profile_id: 'binance-usdm-main',
      account_id: 'binance-usdm-main:default',
      execution_mode: 'LIVE',
      venue: 'BINANCE_USDM',
    },
    health: {
      exchange_status: 'connected',
      connectivity_status: 'CONNECTED',
      rest_sync_status: 'SYNCED',
      stream_status: 'ACTIVE',
      reconciliation_status: 'READY',
      last_synced_at_utc: '2026-04-24T12:00:00Z',
      last_event_seen_at_utc: '2026-04-24T12:00:05Z',
      last_reconciled_at_utc: '2026-04-24T12:00:10Z',
    },
    account: { account_id: 'binance-usdm-main:default', available_balance: 111.11 },
    positions: [{ symbol: 'BTCUSDT' }],
    open_orders: [{ symbol: 'BTCUSDT', order_role: 'PROTECTIVE' }],
    protective_summary: {
      protective_open_order_count: 1,
      trailing_stop_order_count: 1,
      take_profit_order_count: 0,
      stop_loss_order_count: 0,
    },
  })),
  refreshOperateChampionRuntime: vi.fn(async () => ({ ok: true })),
  updateOperateShadowEngine: vi.fn(async () => ({ ok: true })),
  promoteOperateCandidate: vi.fn(async () => ({ ok: true })),
  rollbackOperateChampion: vi.fn(async () => ({ ok: true })),
  syncRuntimeProfileReadOnly: vi.fn(async () => ({ ok: true, sync: { status: 'SYNCED' } })),
}))

describe('OperateControlPageRoute', () => {
  it('defaults to paper-main scope and renders explicit scoped operate posture', async () => {
    renderWithRouter(<OperateControlPageRoute />, { route: '/operate/control' })

    await waitFor(() => expect(screen.getByRole('button', { name: 'paper-main' })).toBeInTheDocument())

    expect(screen.getByText('Profile paper-main')).toBeInTheDocument()
    expect(screen.getByText('Account paper-main:default')).toBeInTheDocument()
    expect(screen.getByText('PAPER · paper')).toBeInTheDocument()
    expect(screen.getByText('Scoped runtime state')).toBeInTheDocument()
    expect(screen.getByText('Resolved config hash: hash-123')).toBeInTheDocument()
    expect(screen.getByText('Registry, champion, and model selection remain global until a later Phase 2 slice')).toBeInTheDocument()
  })

  it('renders live profile exposure for the explicit binance runtime profile scope without calling paper balance', async () => {
    vi.mocked(api.fetchPaperBalanceForScope).mockClear()
    renderWithRouter(<OperateControlPageRoute />, { route: '/operate/control?profile=binance-usdm-main' })

    await waitFor(() => expect(screen.getByText('Live profile exposure')).toBeInTheDocument())

    expect(screen.getByText('Profile binance-usdm-main')).toBeInTheDocument()
    expect(screen.getByText('Account binance-usdm-main:default')).toBeInTheDocument()
    expect(screen.getAllByText(/Connectivity:/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/REST sync:/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Protective orders:/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Trailing stops:/).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Sync Binance now' })).toBeInTheDocument()
    expect(screen.getByText('This surface is exposure-first for the selected live profile. Live placement controls are handled elsewhere.')).toBeInTheDocument()
    expect(api.fetchPaperBalanceForScope).not.toHaveBeenCalledWith('binance-usdm-main')
  })
})
