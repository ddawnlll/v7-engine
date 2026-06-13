import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ProfileScopeBar } from './ProfileScopeBar'
import { PROFILE_SCOPE_OPTIONS } from '../../lib/profileScope'
import { renderWithRouter } from '../../test/renderWithRouter'

describe('ProfileScopeBar', () => {
  it('renders a compatibility-safe default and leaves deferred scopes disabled', async () => {
    const onChange = vi.fn()
    renderWithRouter(
      <ProfileScopeBar options={PROFILE_SCOPE_OPTIONS} value="paper-main" onChange={onChange} />,
      { route: '/trade/trades' },
    )

    expect(screen.getByRole('button', { name: 'paper-main' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'All profiles' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Shared learning' })).toBeDisabled()
    expect(screen.getByText(/global navigation and system chrome stay outside this scope/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'paper-main' }))
    expect(onChange).toHaveBeenCalledWith('paper-main')
  })
})
