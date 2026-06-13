import type { ReactElement, ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SettingsProvider } from '../contexts/SettingsContext'

export function renderWithRouter(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SettingsProvider>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </SettingsProvider>
      </QueryClientProvider>
    )
  }

  return render(ui, { wrapper: Wrapper })
}
