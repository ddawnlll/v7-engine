import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ScanJobForm } from './ScanJobForm'
import { renderWithRouter } from '../../test/renderWithRouter'

describe('ScanJobForm', () => {
  it('submits selected markets, intervals, modes, and worker count', async () => {
    const onSubmit = vi.fn()
    renderWithRouter(
      <ScanJobForm
        onSubmit={onSubmit}
        isSubmitting={false}
        availableSymbols={['BTCUSDT', 'ETHUSDT', 'SOLUSDT']}
        availableIntervals={['15m', '1h']}
        availableModes={['SCALP', 'SWING']}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'ETHUSDT' }))
    await userEvent.click(screen.getByRole('button', { name: '1 worker' }))
    await userEvent.click(screen.getByRole('button', { name: /submit scan job/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      symbols: ['BTCUSDT', 'SOLUSDT'],
      intervals: ['15m', '1h'],
      modes: ['SCALP', 'SWING'],
      scan_workers: 1,
    })
  })

  it('can select all symbols before submitting', async () => {
    const onSubmit = vi.fn()
    renderWithRouter(
      <ScanJobForm
        onSubmit={onSubmit}
        isSubmitting={false}
        availableSymbols={['BTCUSDT', 'ETHUSDT', 'SOLUSDT']}
        availableIntervals={['15m', '1h']}
        availableModes={['SCALP', 'SWING']}
      />,
    )

    await userEvent.click(screen.getAllByRole('button', { name: /select all/i })[0])
    await userEvent.click(screen.getByRole('button', { name: /submit scan job/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
      intervals: ['15m', '1h'],
      modes: ['SCALP', 'SWING'],
      scan_workers: 4,
    })
  })

  it('supports higher worker count selections', async () => {
    const onSubmit = vi.fn()
    renderWithRouter(
      <ScanJobForm
        onSubmit={onSubmit}
        isSubmitting={false}
        availableSymbols={['BTCUSDT', 'ETHUSDT', 'SOLUSDT']}
        availableIntervals={['15m', '1h']}
        availableModes={['SCALP', 'SWING']}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: '16 workers' }))
    await userEvent.click(screen.getByRole('button', { name: /submit scan job/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
      intervals: ['15m', '1h'],
      modes: ['SCALP', 'SWING'],
      scan_workers: 16,
    })
  })

  it('supports very high worker count selections', async () => {
    const onSubmit = vi.fn()
    renderWithRouter(
      <ScanJobForm
        onSubmit={onSubmit}
        isSubmitting={false}
        availableSymbols={['BTCUSDT', 'ETHUSDT', 'SOLUSDT']}
        availableIntervals={['15m', '1h']}
        availableModes={['SCALP', 'SWING']}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: '128 workers' }))
    await userEvent.click(screen.getByRole('button', { name: /submit scan job/i }))

    expect(onSubmit).toHaveBeenCalledWith({
      symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
      intervals: ['15m', '1h'],
      modes: ['SCALP', 'SWING'],
      scan_workers: 128,
    })
  })
})
