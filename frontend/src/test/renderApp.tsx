import { render } from '@testing-library/react'
import { MemoryRouter, useRoutes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { appRoutes } from '@/routes'

function RoutedApp() {
  return useRoutes(appRoutes)
}

/**
 * Mounts the REAL application route table (same config as production) at a given
 * path via MemoryRouter + useRoutes. This exercises the exact guards and route
 * separation that ship, without the data-router's internal Request machinery
 * (which trips over jsdom's AbortSignal realm).
 */
export function renderApp(initialPath: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <RoutedApp />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}
