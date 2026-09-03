import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { RespondPanel } from './RespondPanel'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: (globalThis as any).__testProfile }),
}))

vi.mock('@/api/hooks/docvault', () => ({
  useDocuments: () => ({ data: [] }),
}))

vi.mock('@/api/hooks/auditease', () => ({
  useRespondToRequirement: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

const baseReq = {
  id: 'req-1',
  status: 'open',
  requirement_id_str: 'REQ-001',
  submission_count: 0,
} as any

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('RespondPanel DocVault picker gate', () => {
  it('hides "Select from DocVault" when the user lacks docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['auditease'] }
    renderWithProviders(<RespondPanel engagementId="eng-1" req={baseReq} />)
    expect(screen.queryByText('Select from DocVault')).not.toBeInTheDocument()
  })

  it('shows "Select from DocVault" when the user has docvault access', () => {
    ;(globalThis as any).__testProfile = { role: 'employee', accessible_modules: ['auditease', 'docvault'] }
    renderWithProviders(<RespondPanel engagementId="eng-1" req={baseReq} />)
    expect(screen.getByText('Select from DocVault')).toBeInTheDocument()
  })
})
