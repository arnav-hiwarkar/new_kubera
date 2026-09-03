import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import { saveBlob } from '@/lib/download'
import { QueriesTab } from './QueriesTab'
import { RequirementsTab } from './RequirementsTab'

vi.mock('@/lib/download', () => ({ saveBlob: vi.fn() }))
vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: { role: 'employee', accessible_modules: ['auditease', 'docvault'] } }),
}))
vi.mock('@/api/hooks/docvault', () => ({ useDocuments: () => ({ data: [] }) }))

vi.mock('@/api/endpoints/auditease', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints/auditease')>()
  return {
    ...actual,
    auditeaseCompanyApi: {
      ...actual.auditeaseCompanyApi,
      getDocument: vi.fn().mockResolvedValue({
        id: 'doc-1',
        current_version_id: 'v-1',
        versions: [{ id: 'v-1', original_filename: 'report.pdf' }],
      }),
      downloadDocument: vi.fn().mockResolvedValue(new Blob(['x'])),
    },
  }
})

vi.mock('@/api/hooks/auditease', () => ({
  useListQueries: () => ({
    data: [
      {
        id: 'q-1',
        status: 'open',
        requirement_id: null,
        created_at: new Date().toISOString(),
        messages: [
          {
            id: 'm-1',
            sender_type: 'auditor',
            text: 'see attached',
            attached_document_id: 'doc-1',
            created_at: new Date().toISOString(),
          },
        ],
      },
    ],
    isLoading: false,
  }),
  useAddQueryMessage: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRespondToRequirement: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useListRequirements: () => ({
    data: [
      {
        id: 'req-1',
        requirement_id_str: 'REQ-001',
        status: 'open',
        submission_count: 1,
        submissions: [
          { id: 'sub-1', documents: [{ document_id: 'doc-1', filename: 'report.pdf' }] },
        ],
      },
    ],
    isLoading: false,
  }),
}))

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('AuditEase download handlers use the dedicated endpoints', () => {
  it('QueriesTab downloads via getDocument + downloadDocument, not the docvault route', async () => {
    renderWithProviders(<QueriesTab engagementId="eng-1" />)
    fireEvent.click(screen.getByText('see attached'))
    fireEvent.click(screen.getByText('Download Attachment'))
    await waitFor(() => expect(auditeaseCompanyApi.downloadDocument).toHaveBeenCalledWith('doc-1'))
    expect(auditeaseCompanyApi.getDocument).toHaveBeenCalledWith('doc-1')
    expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob), 'report.pdf')
  })

  it('RequirementsTab downloads via downloadDocument using the already-known filename', async () => {
    renderWithProviders(<RequirementsTab engagementId="eng-1" />)
    fireEvent.click(screen.getByLabelText('Expand requirement'))
    fireEvent.click(screen.getByText('report.pdf'))
    await waitFor(() => expect(auditeaseCompanyApi.downloadDocument).toHaveBeenCalledWith('doc-1'))
    expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob), 'report.pdf')
  })
})
