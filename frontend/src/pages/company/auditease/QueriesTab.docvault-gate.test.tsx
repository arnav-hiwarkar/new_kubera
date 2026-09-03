import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { QueriesTab } from './QueriesTab'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: (globalThis as any).__testProfile }),
}))

vi.mock('@/api/hooks/docvault', () => ({
  useDocuments: () => ({ data: [] }),
  useDownloadDocument: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('@/api/hooks/auditease', () => ({
  useListQueries: () => ({
    data: [
      {
        id: 'q-1',
        status: 'open',
        requirement_id: null,
        created_at: new Date().toISOString(),
        messages: [{ id: 'm-1', sender_type: 'company_user', text: 'hi', created_at: new Date().toISOString() }],
      },
    ],
    isLoading: false,
  }),
  useAddQueryMessage: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('QueriesTab DocVault picker gate', () => {
  it('hides "Select from DocVault" when the user lacks docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['auditease'] }
    renderWithProviders(<QueriesTab engagementId="eng-1" />)
    fireEvent.click(screen.getByText(/No messages|hi/))
    expect(screen.queryByText('Select from DocVault')).not.toBeInTheDocument()
  })

  it('shows "Select from DocVault" when the user has docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['auditease', 'docvault'] }
    renderWithProviders(<QueriesTab engagementId="eng-1" />)
    fireEvent.click(screen.getByText(/No messages|hi/))
    expect(screen.getByText('Select from DocVault')).toBeInTheDocument()
  })
})
