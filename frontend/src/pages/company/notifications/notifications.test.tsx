import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { notificationsApi } from '@/api/endpoints/notifications'
import type { NotificationOut } from '@/api/types'
import { NotificationsPage } from './NotificationsPage'

vi.mock('@/api/endpoints/notifications', () => ({
  notificationsApi: {
    list: vi.fn(),
    markRead: vi.fn(),
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

describe('NotificationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders notifications and allows marking as read', async () => {
    const user = userEvent.setup()
    const mockNotif: NotificationOut = {
      id: 'n-1',
      recipient_type: 'company_user',
      recipient_id: 'usr-1',
      type: 'alert',
      payload: { message: 'Something happened' },
      read_at: null,
      created_at: '2026-07-14T00:00:00Z',
    }
    vi.mocked(notificationsApi.list).mockResolvedValue([mockNotif])
    vi.mocked(notificationsApi.markRead).mockResolvedValue({ ...mockNotif, read_at: '2026-07-14T01:00:00Z' })

    wrap(<NotificationsPage />)
    
    await waitFor(() => {
      expect(screen.getByText('Something happened')).toBeInTheDocument()
    })

    const btn = screen.getByRole('button', { name: /mark as read/i })
    await user.click(btn)

    expect(notificationsApi.markRead).toHaveBeenCalledWith('n-1', expect.anything())
  })
})
