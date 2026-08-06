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
    updateMeetingRecord: vi.fn(),
    getBucket: vi.fn(),
    listUnsyncedDocuments: vi.fn(),
    syncFromDocVault: vi.fn(),
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
    domain: 'roc',
    doc_type_id: 'dt1',
    title: 'Board Minutes 2026-07-05',
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
  // Default: nothing waiting in docVault, so the sync button stays hidden.
  vi.mocked(rocApi.listUnsyncedDocuments).mockResolvedValue([])
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
    const now = new Date()
    const currentDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-05`
    const currentMonth = now.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
    vi.mocked(rocApi.listDocumentTypes).mockResolvedValue([docType({ id: 'dt1', name: 'Board Minutes' })])
    vi.mocked(rocApi.listMeetingRecords).mockResolvedValue([
      record({ id: 'r1', record_date: currentDate }),
      record({ id: 'r2', record_date: '2025-03-05' }),
    ])
    const u = userEvent.setup()
    wrap(<RecordsTab domain="roc" />)

    // Both records visible (grouped by type by default → one "Board Minutes" heading with count 2).
    await waitFor(() => expect(screen.getByText(/\(2\)/)).toBeInTheDocument())

    // Switch to By month → two month headings.
    await u.click(screen.getByRole('button', { name: 'By month' }))
    expect(await screen.findByText(new RegExp(currentMonth))).toBeInTheDocument()
    expect(screen.getByText(/March 2025/)).toBeInTheDocument()

    // This month filter → only the July record remains.
    await u.click(screen.getByRole('button', { name: 'This month' }))
    await waitFor(() => expect(screen.queryByText(/March 2025/)).not.toBeInTheDocument())
    expect(screen.getByText(new RegExp(currentMonth))).toBeInTheDocument()
  })

  it('hides the sync button when docVault has nothing new', async () => {
    vi.mocked(rocApi.listDocumentTypes).mockResolvedValue([docType({})])
    vi.mocked(rocApi.listMeetingRecords).mockResolvedValue([record({})])
    wrap(<RecordsTab domain="roc" />)

    await screen.findByText('Board Minutes 2026-07-05')
    expect(screen.queryByRole('button', { name: /Sync from DocVault/ })).not.toBeInTheDocument()
  })

  it('shows the unsynced count and imports on click', async () => {
    vi.mocked(rocApi.listDocumentTypes).mockResolvedValue([docType({})])
    vi.mocked(rocApi.listMeetingRecords).mockResolvedValue([])
    vi.mocked(rocApi.listUnsyncedDocuments).mockResolvedValue([
      { id: 'doc1', title: 'AOC-4', original_filename: 'aoc4.pdf', size_bytes: 10, uploaded_at: null },
      { id: 'doc2', title: 'MGT-7', original_filename: 'mgt7.pdf', size_bytes: 10, uploaded_at: null },
    ])
    vi.mocked(rocApi.syncFromDocVault).mockResolvedValue({ imported: 2, records: [] })
    const u = userEvent.setup()
    wrap(<RecordsTab domain="roc" />)

    const button = await screen.findByRole('button', { name: /Sync from DocVault \(2\)/ })
    await u.click(button)

    await waitFor(() => expect(rocApi.syncFromDocVault).toHaveBeenCalled())
    expect(await screen.findByText(/Imported 2 documents from DocVault/)).toBeInTheDocument()
  })

  it('renders an untyped record as Unclassified without crashing', async () => {
    vi.mocked(rocApi.listDocumentTypes).mockResolvedValue([docType({})])
    vi.mocked(rocApi.listMeetingRecords).mockResolvedValue([
      record({ id: 'r9', doc_type_id: null, title: 'AOC-4', structured_metadata: null }),
    ])
    wrap(<RecordsTab domain="roc" />)

    expect(await screen.findByText('AOC-4')).toBeInTheDocument()
    // Once as the group heading, once as the row subtitle.
    expect(screen.getAllByText(/Unclassified/).length).toBeGreaterThan(0)
  })

  it('prefills the edit modal and PATCHes the record', async () => {
    vi.mocked(rocApi.listDocumentTypes).mockResolvedValue([docType({})])
    vi.mocked(rocApi.listMeetingRecords).mockResolvedValue([
      record({ id: 'r9', doc_type_id: null, title: 'AOC-4', structured_metadata: null, record_date: '2026-06-01' }),
    ])
    vi.mocked(rocApi.updateMeetingRecord).mockResolvedValue(record({}))
    const u = userEvent.setup()
    wrap(<RecordsTab domain="roc" />)

    await u.click(await screen.findByRole('button', { name: 'Edit' }))

    // Prefilled from the record, and no file input in edit mode.
    expect(screen.getByDisplayValue('AOC-4')).toBeInTheDocument()
    expect(screen.queryByText('Completed document')).not.toBeInTheDocument()

    // Classify it, then save.
    await u.selectOptions(screen.getByDisplayValue('— Unclassified —'), 'dt1')
    await u.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(rocApi.updateMeetingRecord).toHaveBeenCalledWith(
        'r9',
        expect.objectContaining({ doc_type_id: 'dt1', title: 'AOC-4', record_date: '2026-06-01' }),
      ),
    )
  })
})
