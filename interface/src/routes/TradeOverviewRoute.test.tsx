import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { TradeOverviewRoute } from './TradeOverviewRoute'
import { renderWithRouter } from '../test/renderWithRouter'

vi.mock('../lib/api', () => ({
  fetchRuntimeProfiles: vi.fn(async () => ({
    items: [{ profile_id: 'paper-main', execution_mode: 'PAPER', venue: 'INTERNAL_PAPER', read_only: false }],
  })),
  fetchTradeOverview: vi.fn(async () => ({
    engine: { active_engine: 'v4' },
    summary: { refresh_seconds: 30, open_trade_count: 1 },
  })),
  fetchEngineHealthForScope: vi.fn(async () => ({
    runtime_readiness: {
      active_engine: 'v4',
      champion_version: 'champ-1',
      runtime_state: 'ready',
      fallback_active: false,
      shadow_status: { active: false },
    },
    analyzer: { active_engine: 'v4', active_engine_version: 'champ-1' },
    runtime_status: 'ready',
  })),
  fetchJobs: vi.fn(async () => ({ pending: 2 })),
  fetchPortfolioForScope: vi.fn(async () => ({
    profile_id: 'paper-main',
    account_id: 'paper-main:default',
    summary: { paper_balance: 1500 },
    paper_account: { account_id: 'paper-main:default', profile_id: 'paper-main', available_balance: 1500 },
    open_positions: [{ order_id: 'ord-1' }],
    portfolio: { open_orders: 1 },
  })),
}))

describe('TradeOverviewRoute', () => {
  it('renders selected profile scope and preserves paper-main overview posture', async () => {
    renderWithRouter(<TradeOverviewRoute />, { route: '/trade/overview' })

    await waitFor(() => expect(screen.getByRole('button', { name: 'paper-main' })).toBeInTheDocument())

    expect(screen.getByText('Profile paper-main')).toBeInTheDocument()
    expect(screen.getByText('Account paper-main:default')).toBeInTheDocument()
    expect(screen.getByText('Engine summary remains global until a later Phase 2 slice')).toBeInTheDocument()
    expect(screen.getByText('Selected profile')).toBeInTheDocument()
    expect(screen.getAllByText('paper-main').length).toBeGreaterThan(0)
    expect(screen.getAllByText('PAPER').length).toBeGreaterThan(0)
  })
})
