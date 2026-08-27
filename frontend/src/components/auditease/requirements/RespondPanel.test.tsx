import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RespondPanel } from './RespondPanel'
import type { RequirementRequestResponse } from '@/api/types'

import { ToastProvider } from '@/components/ui'

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

describe('RespondPanel', () => {
  const openReq: RequirementRequestResponse = {
    id: 'req-1',
    engagement_id: 'eng-1',
    raised_by: 'u1',
    seq_number: 1,
    requirement_id_str: 'REQ-001',
    description: 'Bank stmts',
    priority: 1,
    status: 'open',
    document_count: 0,
    linked_query_count: 0,
    submission_count: 0,
    submissions: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }

  const closedReq: RequirementRequestResponse = {
    ...openReq,
    status: 'closed',
  }

  it('renders form when requirement is open', () => {
    renderWithClient(<RespondPanel engagementId="eng-1" req={openReq} />)
    expect(screen.getByPlaceholderText(/type your explanation/i)).toBeInTheDocument()
    expect(screen.getByText('Attach Files')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit response/i })).toBeInTheDocument()
  })

  it('renders locked banner when requirement is closed', () => {
    renderWithClient(<RespondPanel engagementId="eng-1" req={closedReq} />)
    expect(screen.getByText(/this requirement is/i)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/type your explanation/i)).not.toBeInTheDocument()
  })

  it('shows validation error if submitted empty', () => {
    renderWithClient(<RespondPanel engagementId="eng-1" req={openReq} />)
    const form = screen.getByRole('button', { name: /submit response/i }).closest('form')!
    fireEvent.submit(form)
    expect(
      screen.getByText(/please provide a written answer or attach at least one file/i)
    ).toBeInTheDocument()
  })
})
