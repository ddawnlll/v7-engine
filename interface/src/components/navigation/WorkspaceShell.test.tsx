import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { LayoutDashboard } from 'lucide-react'
import { Routes, Route } from 'react-router-dom'

import { WorkspaceShell } from './WorkspaceShell'
import { renderWithRouter } from '../../test/renderWithRouter'

describe('WorkspaceShell', () => {
  it('preserves profile scope across workspace tab navigation', () => {
    renderWithRouter(
      <Routes>
        <Route
          path="/trade/*"
          element={(
            <WorkspaceShell
              label="Trade"
              description="Live operator views."
              icon={LayoutDashboard}
              tabs={[
                { slug: 'overview', label: 'Overview', to: '/trade/overview' },
                { slug: 'trades', label: 'Trades', to: '/trade/trades' },
                { slug: 'portfolio', label: 'Portfolio', to: '/trade/portfolio' },
              ]}
            />
          )}
        >
          <Route path="trades" element={<div>Trades page</div>} />
        </Route>
      </Routes>,
      { route: '/trade/trades?profile=paper-main' },
    )

    expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('href', '/trade/overview?profile=paper-main')
    expect(screen.getByRole('link', { name: 'Portfolio' })).toHaveAttribute('href', '/trade/portfolio?profile=paper-main')
  })
})
