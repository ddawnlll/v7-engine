import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchInterval: 15_000,
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
})
