import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RequirementCard } from './RequirementCard'
import type { RequirementRequestResponse } from '@/api/types'
import { ToastProvider } from '@/components/ui'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({
    profile: { role: 'admin', accessible_modules: ['auditease', 'docvault'] },
  }),
}))

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('RequirementCard', () => {
  const mockReq: RequirementRequestResponse = {
    id: 'req-123',
    engagement_id: 'eng-456',
    raised_by: 'user-1',
    seq_number: 1,
    requirement_id_str: 'REQ-001',
    description: 'Provide bank statements for FY24',
    priority: 1,
    status: 'open',
    document_count: 1,
    linked_query_count: 0,
    submission_count: 1,
    submissions: [
      {
        id: 'sub-1',
        requirement_id: 'req-123',
        round_number: 1,
        text_answer: 'Uploaded first batch',
        created_at: '2026-01-01T00:00:00Z',
        responded_by_name: 'Alice',
        documents: [
          {
            document_id: 'doc-1',
            filename: 'statements.pdf',
            size_bytes: 1024 * 50,
          },
        ],
      },
    ],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }

  it('renders requirement details and badges', () => {
    renderWithClient(
      <RequirementCard
        req={mockReq}
        variant="auditor"
        engagementId="eng-456"
      />
    )

    expect(screen.getByText('REQ-001')).toBeInTheDocument()
    expect(screen.getByText('Responded')).toBeInTheDocument()
    expect(screen.getByText('P1')).toBeInTheDocument()
    expect(screen.getByText('Provide bank statements for FY24')).toBeInTheDocument()
  })

  it('auditor variant triggers onClose when Close button is clicked', () => {
    const onClose = vi.fn()
    renderWithClient(
      <RequirementCard
        req={mockReq}
        variant="auditor"
        engagementId="eng-456"
        onClose={onClose}
      />
    )

    const closeBtn = screen.getByTitle('Close requirement')
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledWith('req-123')
  })

  it('auditor variant shows Reopen button when closed', () => {
    const closedReq: RequirementRequestResponse = {
      ...mockReq,
      status: 'closed',
    }
    const onReopen = vi.fn()
    renderWithClient(
      <RequirementCard
        req={closedReq}
        variant="auditor"
        engagementId="eng-456"
        onReopen={onReopen}
      />
    )

    expect(screen.getByText('Closed')).toBeInTheDocument()
    const reopenBtn = screen.getByTitle('Reopen requirement')
    fireEvent.click(reopenBtn)
    expect(onReopen).toHaveBeenCalledWith('req-123')
  })

  it('expands to show submission history when toggled', () => {
    renderWithClient(
      <RequirementCard
        req={mockReq}
        variant="company"
        engagementId="eng-456"
      />
    )

    // Initially collapsed, timeline text not in DOM
    expect(screen.queryByText('Submission History (1 round)')).not.toBeInTheDocument()

    // Click expand
    const expandBtn = screen.getByLabelText('Expand requirement')
    fireEvent.click(expandBtn)

    // Submission history and document chip now visible
    expect(screen.getByText('Submission History (1 round)')).toBeInTheDocument()
    expect(screen.getByText('Uploaded first batch')).toBeInTheDocument()
    expect(screen.getByText('statements.pdf')).toBeInTheDocument()
  })

  it('triggers onInitiateQuery when Initiate Query button is clicked', () => {
    const onInitiate = vi.fn()
    renderWithClient(
      <RequirementCard
        req={mockReq}
        variant="auditor"
        engagementId="eng-456"
        onInitiateQuery={onInitiate}
      />
    )

    const queryBtn = screen.getByRole('button', { name: /Initiate Query/i })
    fireEvent.click(queryBtn)
    expect(onInitiate).toHaveBeenCalledWith(mockReq)
  })

  it('renders linked query badge when linked_query_count > 0', () => {
    const reqWithQueries: RequirementRequestResponse = {
      ...mockReq,
      linked_query_count: 2,
    }
    const onViewQueries = vi.fn()
    renderWithClient(
      <RequirementCard
        req={reqWithQueries}
        variant="auditor"
        engagementId="eng-456"
        onViewQueries={onViewQueries}
      />
    )

    const queryBadge = screen.getByText('2 queries')
    expect(queryBadge).toBeInTheDocument()
    fireEvent.click(queryBadge)
    expect(onViewQueries).toHaveBeenCalledWith(reqWithQueries)
  })
})

