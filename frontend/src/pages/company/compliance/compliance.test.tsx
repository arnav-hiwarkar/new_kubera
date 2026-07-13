import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import type { DocumentTypeResponse, MeetingRecordResponse } from '@/api/types'
import { rocApi } from '@/api/endpoints/compliance'
import { DocumentTypesTab } from './DocumentTypesTab'
import { RecordsTab } from './RecordsTab'

vi.mock('@/api/endpoints/compliance', () => {
  const api = {
    listDocumentTypes: vi.fn(),
    createDocumentType: vi.fn(),
    updateDocumentType: vi.fn(),
    deleteDocumentType: vi.fn(),
    listMeetingRecords: vi.fn(),
    createMeetingRecord: vi.fn(),
  }
  return { rocApi: api, secretarialApi: api }
})

vi.mock('@/api/endpoints/docvault', () => ({
  docvaultApi: {
    listBuckets: vi.fn().mockResolvedValue([]),
    createBucket: vi.fn(),
    uploadDocument: vi.fn(),
    downloadDocument: vi.fn(),
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

function docType(over: Partial<DocumentTypeResponse>): DocumentTypeResponse {
  return {
    id: 'dt1',
    company_id: 'co1',
    domain: 'roc',
    name: 'Board Minutes',
    template_file_id: null,
    metadata_schema: { fields: [{ key: 'meeting_date', label: 'Meeting date', type: 'date' }] },
    due_date_rule: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

function record(over: Partial<MeetingRecordResponse>): MeetingRecordResponse {
  return {
    id: 'r1',
    company_id: 'co1',
    doc_type_id: 'dt1',
    document_id: 'doc1',
    structured_metadata: { meeting_date: '2026-07-05' },
    record_date: '2026-07-05',
    created_at: '2026-07-05T00:00:00Z',
    updated_at: '2026-07-05T00:00:00Z',
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DocumentTypesTab', () => {
  it('renders system and company types', async () => {
    vi.mocked(rocApi.listDocumentTypes).mockResolvedValue([
      docType({ id: 'sys', company_id: null, name: 'AGM Notice' }),
      docType({ id: 'co', company_id: 'co1', name: 'Board Minutes' }),
    ])
    wrap(<DocumentTypesTab domain="roc" />)

    expect(await screen.findByText('AGM Notice')).toBeInTheDocument()
    expect(screen.getByText('Board Minutes')).toBeInTheDocument()
    expect(screen.getByText('System')).toBeInTheDocument()
    expect(screen.getByText('Company')).toBeInTheDocument()
  })

  it('creates a type with a field via the modal', async () => {
    vi.mocked(rocApi.listDocumentTypes).mockResolvedValue([])
    vi.mocked(rocApi.createDocumentType).mockResolvedValue(docType({}))
    const u = userEvent.setup()
    wrap(<DocumentTypesTab domain="roc" />)

    await u.click(await screen.findByRole('button', { name: 'New type' }))
    await u.type(screen.getByPlaceholderText('e.g. Board Meeting Minutes'), 'Annual Return')
    await u.click(screen.getByRole('button', { name: 'Add field' }))
    await u.type(screen.getByPlaceholderText('e.g. Meeting date'), 'Filing period')
    await u.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() =>
      expect(rocApi.createDocumentType).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Annual Return',
          metadata_schema: {
            fields: expect.arrayContaining([
              expect.objectContaining({ key: 'filing_period', label: 'Filing period', type: 'text' }),
            ]),
          },
        }),
      ),
    )
  })
})

describe('RecordsTab', () => {
  it('renders records, filters by this month, and toggles views', async () => {
    vi.mocked(rocApi.listDocumentTypes).mockResolvedValue([docType({ id: 'dt1', name: 'Board Minutes' })])
    vi.mocked(rocApi.listMeetingRecords).mockResolvedValue([
      record({ id: 'r1', record_date: '2026-07-05' }),
      record({ id: 'r2', record_date: '2026-03-05' }),
    ])
    const u = userEvent.setup()
    wrap(<RecordsTab domain="roc" />)

    // Both records visible (grouped by type by default → one "Board Minutes" heading with count 2).
    await waitFor(() => expect(screen.getByText(/\(2\)/)).toBeInTheDocument())

    // Switch to By month → two month headings.
    await u.click(screen.getByRole('button', { name: 'By month' }))
    expect(await screen.findByText(/July 2026/)).toBeInTheDocument()
    expect(screen.getByText(/March 2026/)).toBeInTheDocument()

    // This month filter → only the July record remains.
    await u.click(screen.getByRole('button', { name: 'This month' }))
    await waitFor(() => expect(screen.queryByText(/March 2026/)).not.toBeInTheDocument())
    expect(screen.getByText(/July 2026/)).toBeInTheDocument()
  })
})
