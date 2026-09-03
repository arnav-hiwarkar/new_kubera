import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RespondPanel } from './RespondPanel'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import type { RequirementRequestResponse } from '@/api/types'
import { ToastProvider } from '@/components/ui'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({
    profile: { role: 'admin', accessible_modules: ['auditease', 'docvault'] },
  }),
}))

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

  it('renders form and dropzone when requirement is open', () => {
    renderWithClient(<RespondPanel engagementId="eng-1" req={openReq} />)
    expect(screen.getByPlaceholderText(/type your explanation/i)).toBeInTheDocument()
    expect(screen.getByText('Browse device')).toBeInTheDocument()
    expect(screen.getByText('Select from DocVault')).toBeInTheDocument()
    expect(screen.getByText(/upload documents from your machine/i)).toBeInTheDocument()
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
      screen.getByText(/please provide a written answer or attach at least one document/i)
    ).toBeInTheDocument()
  })

  it('stages local files from input and allows removing them', () => {
    const { container } = renderWithClient(<RespondPanel engagementId="eng-1" req={openReq} />)
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).toBeInTheDocument()

    const mockFile = new File(['test content'], 'bank_statement.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    expect(screen.getByText('bank_statement.pdf')).toBeInTheDocument()
    expect(screen.getByText(/1 document staged for submission/i)).toBeInTheDocument()

    // Remove file
    const removeBtn = screen.getByTitle('Remove file')
    fireEvent.click(removeBtn)

    expect(screen.queryByText('bank_statement.pdf')).not.toBeInTheDocument()
  })

  it('submits response with written answer and files', async () => {
    const respondSpy = vi.spyOn(auditeaseCompanyApi, 'respondRequirement').mockResolvedValue({
      ...openReq,
      submission_count: 1,
    })
    const onSuccess = vi.fn()

    const { container } = renderWithClient(
      <RespondPanel engagementId="eng-1" req={openReq} onSuccess={onSuccess} />
    )

    const textarea = screen.getByPlaceholderText(/type your explanation/i)
    fireEvent.change(textarea, { target: { value: 'Here are the requested statements' } })

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
    const mockFile = new File(['file data'], 'march_pnl.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [mockFile] } })

    const submitBtn = screen.getByRole('button', { name: /submit response/i })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(respondSpy).toHaveBeenCalledWith('eng-1', 'req-1', expect.any(FormData))
      expect(onSuccess).toHaveBeenCalled()
    })
  })
})
