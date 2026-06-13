import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { PortfolioRoute } from './PortfolioRoute'
import { renderWithRouter } from '../test/renderWithRouter'

vi.mock('../lib/api', () => ({
  fetchRuntimeProfiles: vi.fn(async () => ({
    items: [{ profile_id: 'paper-main', execution_mode: 'PAPER', venue: 'INTERNAL_PAPER', read_only: false }],
  })),
  syncRuntimeProfileReadOnly: vi.fn(async () => ({ ok: true })),
  fetchPortfolioForScope: vi.fn(async () => ({
    profile_id: 'paper-main',
    account_id: 'paper-main:default',
    generated_at: '2026-04-23T12:00:00Z',
    summary: {
      paper_balance: 1200,
      total_equity: 1250,
      net_r: 2.5,
      win_rate: 60,
      profit_factor: 1.4,
      total_trades: 5,
      today_pnl: 25,
      today_pnl_pct: 2.1,
      three_day_pnl: 40,
      three_day_pnl_pct: 3.2,
      invested_capital: 300,
      performance_windows: { today: { closed_trades: 1 } },
    },
    portfolio: {
      open_orders: 1,
      total_orders: 5,
      total_equity: 1250,
    },
    paper_account: {
      account_id: 'paper-main:default',
      profile_id: 'paper-main',
      balance_ccy: 'USD',
      available_balance: 1200,
      equity: 1250,
      margin_used: 0,
      default_balance: 1000,
    },
    avg_hold_minutes: 45,
    daily: [],
    recent_closed: [],
    open_positions: [
      {
        order_id: 'ord-1',
        profile_id: 'paper-main',
        execution_mode: 'PAPER',
        venue: 'paper',
        origin: 'AUTO',
        symbol: 'BTCUSDT',
        direction: 'BUY',
        source: 'PAPER',
        entry: 100,
        sl: 95,
        tp: 110,
        confidence: 0.7,
        open_timestamp: '2026-04-23T10:00:00Z',
      },
    ],
    engine: {
      thread_alive: true,
      last_scan: { timestamp: new Date().toISOString() },
    },
    equity_curve: [],
  })),
}))

describe('PortfolioRoute', () => {
  it('defaults safely to paper-main scope and renders profile-aware account context', async () => {
    renderWithRouter(<PortfolioRoute />, { route: '/trade/portfolio' })

    await waitFor(() => expect(screen.getByRole('button', { name: 'paper-main' })).toBeInTheDocument())

    expect(screen.getByText('Profile paper-main')).toBeInTheDocument()
    expect(screen.getByText('Account paper-main:default')).toBeInTheDocument()
    expect(screen.getAllByText('Available Balance').length).toBeGreaterThan(0)
    expect(screen.getByText('Execution')).toBeInTheDocument()
    expect(screen.getByText('PAPER · AUTO')).toBeInTheDocument()
  })
})
