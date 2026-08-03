import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/http'
import { ApiContractError } from '@/api/contracts/trialBalance'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiContractError) return false
        // Never retry auth/client errors — only transient failures.
        if (error instanceof ApiError && error.status < 500) return false
        return failureCount < 2
      },
      refetchOnWindowFocus: false,
    },
  },
})
