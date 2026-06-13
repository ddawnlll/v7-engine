import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'

import { Navbar } from './Navbar'
import { renderWithRouter } from '../../test/renderWithRouter'

describe('Navbar scan controls', () => {
  it('renders pause, resume, stop, and scan-now controls with expected enablement', () => {
    const onPauseScans = vi.fn()
    const onResumeScans = vi.fn()
    const onStopScans = vi.fn()
    const onTriggerScanNow = vi.fn()

    renderWithRouter(
      <Navbar
        engineLabel="healthy"
        engineTone="good"
        alerts={[]}
        availableSymbols={[]}
        onPauseScans={onPauseScans}
        onResumeScans={onResumeScans}
        onStopScans={onStopScans}
        onTriggerScanNow={onTriggerScanNow}
        isScanPaused={false}
        hasActiveScan={true}
        stopRequested={false}
      />,
      { route: '/trade/overview' },
    )

    expect(screen.getByRole('button', { name: /pause/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /resume/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /stop/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /scan now/i })).toBeEnabled()
  })

  it('shows linked engine degradation detail when provided', () => {
    renderWithRouter(
      <Navbar
        engineLabel="degraded"
        engineTone="warn"
        engineDetail="user data stream reconnect required"
        engineDetailHref="/operate/control"
        alerts={[]}
        availableSymbols={[]}
      />,
      { route: '/trade/overview?profile=binance-usdm-main' },
    )

    const detail = screen.getByRole('link', { name: /user data stream reconnect required/i })
    expect(detail).toBeInTheDocument()
    expect(detail.getAttribute('href')).toContain('/operate/control')
    expect(detail.getAttribute('href')).toContain('profile=binance-usdm-main')
  })

  it('renders a profile selector and emits scope changes', () => {
    const onProfileScopeChange = vi.fn()

    renderWithRouter(
      <Navbar
        engineLabel="healthy"
        engineTone="good"
        alerts={[]}
        availableSymbols={[]}
        profileOptions={[
          { value: 'paper-main', label: 'paper-main', kind: 'profile', enabled: true },
          { value: 'binance-usdm-main', label: 'binance-usdm-main', kind: 'profile', enabled: true },
        ]}
        activeProfileScope="paper-main"
        onProfileScopeChange={onProfileScopeChange}
      />,
      { route: '/trade/overview' },
    )

    fireEvent.change(screen.getByRole('combobox', { name: /select profile/i }), {
      target: { value: 'binance-usdm-main' },
    })

    expect(onProfileScopeChange).toHaveBeenCalledWith('binance-usdm-main')
  })
})
