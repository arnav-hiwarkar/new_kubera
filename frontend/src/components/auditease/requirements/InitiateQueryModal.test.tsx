import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { InitiateQueryModal } from './InitiateQueryModal'
import type { RequirementRequestResponse } from '@/api/types'
import { auditorEngagementsApi } from '@/api/endpoints/auditorEngagements'

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('InitiateQueryModal', () => {
  const mockReq: RequirementRequestResponse = {
    id: 'req-123',
    engagement_id: 'eng-456',
    raised_by: 'user-1',
    seq_number: 1,
    requirement_id_str: 'REQ-001',
    description: 'Please upload FY24 trial balance ledger breakdown',
    priority: 1,
    status: 'open',
    document_count: 0,
    linked_query_count: 0,
    submission_count: 0,
    submissions: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }

  it('renders modal with requirement details', () => {
    renderWithClient(
      <InitiateQueryModal
        open
        onClose={vi.fn()}
        engagementId="eng-456"
        req={mockReq}
      />
    )
    expect(screen.getByText('Initiate Query from Requirement')).toBeInTheDocument()
    expect(screen.getByText('REQ-001')).toBeInTheDocument()
    expect(screen.getByText('Please upload FY24 trial balance ledger breakdown')).toBeInTheDocument()
  })

  it('submits query with requirement_id and initial_message', async () => {
    const createQuerySpy = vi.spyOn(auditorEngagementsApi, 'createQuery').mockResolvedValueOnce({
      id: 'query-999',
      engagement_id: 'eng-456',
      opened_by: 'auditor-1',
      requirement_id: 'req-123',
      status: 'open',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      messages: [],
    })

    const onSuccess = vi.fn()
    const onClose = vi.fn()

    renderWithClient(
      <InitiateQueryModal
        open
        onClose={onClose}
        engagementId="eng-456"
        req={mockReq}
        onSuccess={onSuccess}
      />
    )

    const textarea = screen.getByPlaceholderText(/Ask a specific question/i)
    fireEvent.change(textarea, { target: { value: 'Could you clarify line 5?' } })

    const submitBtn = screen.getByRole('button', { name: /Initiate Query/i })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(createQuerySpy).toHaveBeenCalled()
      expect(onSuccess).toHaveBeenCalledWith('query-999')
      expect(onClose).toHaveBeenCalled()
    })
  })
})
