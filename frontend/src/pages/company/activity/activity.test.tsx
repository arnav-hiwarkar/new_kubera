import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { activityApi } from '@/api/endpoints/activity'
import type { ActivityLogOut } from '@/api/types'
import { ActivityLogPage } from './ActivityLogPage'

vi.mock('@/api/endpoints/activity', () => ({
  activityApi: {
    list: vi.fn(),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ActivityLogPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a list of activity logs', async () => {
    const mockLog: ActivityLogOut = {
      id: 'log-1',
      company_id: 'co-1',
      actor_type: 'company_user',
      actor_id: 'usr-1',
      action: 'created_report',
      entity_type: 'document',
      entity_id: 'doc-1',
      created_at: '2026-07-14T00:00:00Z',
    }
    vi.mocked(activityApi.list).mockResolvedValue([mockLog])

    wrap(<ActivityLogPage />)
    
    await waitFor(() => {
      expect(screen.getByText('Created Report')).toBeInTheDocument()
      expect(screen.getByText('Document')).toBeInTheDocument()
    })
  })
})
