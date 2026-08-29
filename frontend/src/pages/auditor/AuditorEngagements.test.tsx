import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '@/components/ui/Toast'
import { AuditorEngagements } from './AuditorEngagements'

vi.mock('@/api/hooks/auditorEngagements', () => ({
  useAuditorEngagements: () => ({
    data: [
      { id: 'eng-1', period_label: 'FY 2025-26', status: 'active', company_name: 'Acme Audit Co' },
      { id: 'eng-2', period_label: 'FY 2024-25', status: 'invited', company_name: null },
    ],
    isLoading: false,
  }),
  useAcceptEngagement: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

function renderPage() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <AuditorEngagements />
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('AuditorEngagements', () => {
  it('shows the company name for each engagement', () => {
    renderPage()
    expect(screen.getByText('Acme Audit Co')).toBeInTheDocument()
  })

  it('falls back to a placeholder when company_name is missing', () => {
    renderPage()
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
