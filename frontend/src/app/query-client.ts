import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '@/api/http-client'

const STALE_TIME_MS = 30_000
const MAX_RETRIES = 2

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: STALE_TIME_MS,
      // Ответ 4xx не исправится повтором; повторяем только сетевые сбои и 5xx.
      retry: (failureCount, error) =>
        failureCount < MAX_RETRIES && !(error instanceof ApiError && error.status < 500),
    },
  },
})
