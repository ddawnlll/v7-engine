import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { toast } from 'sonner'
import userEvent from '@testing-library/user-event'

import { TradesRoute } from './TradesRoute'
import { renderWithRouter } from '../test/renderWithRouter'

vi.mock('../lib/api', () => ({
  syncRuntimeProfileReadOnly: vi.fn(async () => ({ ok: true, sync: { status: 'SYNCED' } })),
  fetchRuntimeProfiles: vi.fn(async () => ({
    items: [{ profile_id: 'paper-main', execution_mode: 'PAPER', venue: 'INTERNAL_PAPER', read_only: false }],
  })),
  fetchOrdersForScope: vi.fn(async () => ({
    open_orders: [
      {
        order_id: 'ord-1',
        profile_id: 'paper-main',
        execution_mode: 'PAPER',
        venue: 'paper',
        origin: 'MANUAL',
        symbol: 'BTCUSDT',
        direction: 'BUY',
        position_side: 'LONG',
        status: 'OPEN',
        open_timestamp: '2026-04-23T10:00:00Z',
        holding_minutes: 5,
        entry: 100,
        sl: 95,
        tp: 110,
        source: 'PAPER',
      },
    ],
    closed_orders: [],
    manual_open_orders: [],
    manual_closed_orders: [],
    auto_open_orders: [],
    auto_closed_orders: [],
    summary: { open: 1, closed: 0, total: 1, net_r: 0, expected_net_r: 0 },
    open_trade_analysis: {},
  })),
  getFailures: vi.fn(async () => ({ items: [] })),
  getSelfLearningReplays: vi.fn(async () => ({ items: [] })),
  getSignalAudit: vi.fn(async () => ({ ok: true, audit: null })),
  closeOrder: vi.fn(),
  closeAllOpenOrders: vi.fn(),
}))

describe('TradesRoute', () => {
  it('shows a Binance sync button for live Binance profiles and triggers a manual sync', async () => {
    const { TradesRoute: _TradesRoute } = await import('./TradesRoute')
    const api = await import('../lib/api')
    const syncMock = vi.mocked(api.syncRuntimeProfileReadOnly)
    const successSpy = vi.spyOn(toast, 'success').mockImplementation(() => '')

    vi.mocked(api.fetchRuntimeProfiles).mockResolvedValueOnce({
      items: [
        {
          profile_id: 'binance-usdm-main',
          execution_mode: 'LIVE',
          venue: 'BINANCE_USDM',
          read_only: false,
          supports_account_reads: true,
        },
      ],
    })
    vi.mocked(api.fetchOrdersForScope).mockResolvedValueOnce({
      open_orders: [
        {
          order_id: 'live-1',
          profile_id: 'binance-usdm-main',
          execution_mode: 'LIVE',
          venue: 'BINANCE_USDM',
          origin: 'AUTO',
          source: 'AUTO',
          symbol: 'BTCUSDT',
          direction: 'BUY',
          position_side: 'LONG',
          status: 'FILLED',
          open_timestamp: '2026-04-23T10:00:00Z',
          holding_minutes: 5,
          entry: 100,
          sl: 95,
          tp: 110,
        },
      ],
      closed_orders: [],
      manual_open_orders: [],
      manual_closed_orders: [],
      auto_open_orders: [],
      auto_closed_orders: [],
      summary: { open: 1, closed: 0, total: 1, net_r: 0, expected_net_r: 0 },
      open_trade_analysis: {},
    })

    renderWithRouter(<_TradesRoute />, { route: '/trade/trades?profile=binance-usdm-main' })

    const syncButton = await screen.findByRole('button', { name: /sync now/i })
    expect(syncButton).toBeInTheDocument()

    await userEvent.click(syncButton)

    await waitFor(() => expect(syncMock).toHaveBeenCalledWith('binance-usdm-main'))
    await waitFor(() => expect(successSpy).toHaveBeenCalledWith('Synced orders from Binance.'))
  })

  it('renders profile-aware trade identity while preserving paper-main defaults', async () => {
    renderWithRouter(<TradesRoute />, { route: '/trade/trades' })

    await waitFor(() => expect(screen.getByRole('button', { name: 'paper-main' })).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('BTCUSDT')).toBeInTheDocument())

    expect(screen.getByText('Scope paper-main')).toBeInTheDocument()
    expect(screen.getAllByText('paper-main').length).toBeGreaterThan(0)
    expect(screen.getAllByText('PAPER').length).toBeGreaterThan(0)
  })
})
