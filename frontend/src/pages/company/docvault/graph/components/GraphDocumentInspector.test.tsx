import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { GraphDocumentInspector } from './GraphDocumentInspector'
import type { BucketResponse, DocumentResponse } from '@/api/types'
import { docvaultApi } from '@/api/endpoints/docvault'
import { saveBlob } from '@/lib/download'

vi.mock('@/lib/download', () => ({
  saveBlob: vi.fn(),
}))

// Render tabs instantly — skip enter/exit animations in jsdom
vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  motion: {
    div: ({
      children,
      initial: _initial,
      animate: _animate,
      exit: _exit,
      transition: _transition,
      layout: _layout,
      ...rest
    }: React.HTMLAttributes<HTMLDivElement> & Record<string, unknown>) => (
      <div {...rest}>{children}</div>
    ),
  },
}))

vi.mock('@/api/endpoints/docvault', () => ({
  docvaultApi: {
    uploadDocument: vi.fn().mockResolvedValue({}),
    deleteDocument: vi.fn().mockResolvedValue(undefined),
    updateDocument: vi.fn().mockResolvedValue({}),
    uploadVersion: vi.fn().mockResolvedValue({}),
    downloadDocument: vi.fn().mockResolvedValue(new Blob()),
    listDocuments: vi.fn().mockResolvedValue([]),
    listBuckets: vi.fn().mockResolvedValue([]),
  },
}))

type UserEvent = ReturnType<typeof userEvent.setup>

async function goToTab(user: UserEvent, tab: 'edit' | 'versions') {
  await user.click(screen.getByTestId(`inspector-tab-${tab}`))
}

function renderComponent(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
}

const mockBuckets: BucketResponse[] = [
  {
    id: 'bucket-1',
    name: 'Finance & Tax',
    company_id: 'co-1',
    created_by: 'u-1',
    visibility: 'everyone',
    access_user_ids: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'bucket-2',
    name: 'Legal & Board',
    company_id: 'co-1',
    created_by: 'u-1',
    visibility: 'restricted',
    access_user_ids: ['u-1'],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const mockDoc: DocumentResponse = {
  id: 'doc-1',
  company_id: 'co-1',
  current_version_id: 'v-2',
  bucket_id: 'bucket-1',
  status: 'uploaded',
  title: 'Q3 Board Minutes',
  doc_type_id: null,
  tags: ['board', 'minutes'],
  is_editable: true,
  created_by: 'u-1',
  created_by_name: 'Ada Lovelace',
  created_at: '2026-06-01T10:00:00Z',
  updated_at: '2026-06-02T12:00:00Z',
  versions: [
    {
      id: 'v-1',
      document_id: 'doc-1',
      original_filename: 'minutes_draft.pdf',
      mime_type: 'application/pdf',
      size_bytes: 2048,
      checksum: 'chk-1',
      uploaded_by: 'u-1',
      uploaded_by_name: 'Ada Lovelace',
      uploaded_at: '2026-06-01T10:00:00Z',
      version_number: 1,
    },
    {
      id: 'v-2',
      document_id: 'doc-1',
      original_filename: 'minutes_final.pdf',
      mime_type: 'application/pdf',
      size_bytes: 4096,
      checksum: 'chk-2',
      uploaded_by: 'u-2',
      uploaded_by_name: 'Charles Babbage',
      uploaded_at: '2026-06-02T12:00:00Z',
      version_number: 2,
    },
  ],
}

describe('GraphDocumentInspector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when open is false or document is null', () => {
    renderComponent(
      <GraphDocumentInspector
        open={false}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('graph-document-inspector')).not.toBeInTheDocument()

    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={null}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )
    expect(screen.queryByTestId('graph-document-inspector')).not.toBeInTheDocument()
  })

  it('renders document header, subtitle badges, and metadata', () => {
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    const inspector = screen.getByTestId('graph-document-inspector')
    expect(inspector).toBeInTheDocument()

    // Title
    expect(screen.getByTestId('inspector-document-title')).toHaveTextContent('Q3 Board Minutes')

    // Subtitle badges: status, bucket, version
    expect(screen.getByTitle('Finance & Tax')).toBeInTheDocument()
    expect(within(inspector).getAllByText('v2').length).toBeGreaterThanOrEqual(1)

    // Metadata
    expect(within(inspector).getAllByText('Ada Lovelace').length).toBeGreaterThanOrEqual(1)
    expect(within(inspector).getByText('Charles Babbage')).toBeInTheDocument()
    expect(within(inspector).getAllByText('2 Jun 2026').length).toBeGreaterThanOrEqual(1)
  })

  it('calls onClose when close button is clicked', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={onClose}
      />,
    )

    const closeBtn = screen.getByTestId('inspector-close-btn')
    await user.click(closeBtn)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('handles inline title edit and save', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')

    const nameInput = screen.getByDisplayValue('Q3 Board Minutes')
    const nameSection = nameInput.closest('div')!
    const saveBtn = within(nameSection).getByRole('button', { name: 'Save' })

    // Save disabled initially because title is unchanged
    expect(saveBtn).toBeDisabled()

    await user.clear(nameInput)
    await user.type(nameInput, 'Q3 Board Minutes Updated')
    expect(saveBtn).toBeEnabled()

    await user.click(saveBtn)
    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-1', {
        title: 'Q3 Board Minutes Updated',
      }),
    )
  })

  it('handles toggling editable switch', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')

    const switchInput = screen.getByRole('checkbox')
    expect(switchInput).toBeChecked()

    await user.click(switchInput)
    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-1', {
        is_editable: false,
      }),
    )
  })

  it('handles changing status from select dropdown', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')

    // Find the status select
    const statusSelect = screen.getByDisplayValue('Uploaded')
    await user.selectOptions(statusSelect, 'pending_approval')

    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-1', {
        status: 'pending_approval',
      }),
    )
  })

  it('handles changing bucket from select dropdown', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')

    const bucketSelect = screen.getByDisplayValue('Finance & Tax')
    await user.selectOptions(bucketSelect, 'bucket-2')

    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-1', {
        bucket_id: 'bucket-2',
      }),
    )

    // Also test moving to Uncategorized (empty string -> null)
    await user.selectOptions(bucketSelect, '')
    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-1', {
        bucket_id: null,
      }),
    )
  })

  it('handles editing and saving tags', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')

    const tagsInput = screen.getByDisplayValue('board, minutes')
    const tagsSection = tagsInput.closest('div')!
    const saveTagsBtn = within(tagsSection).getByRole('button', { name: 'Save' })

    await user.clear(tagsInput)
    await user.type(tagsInput, 'governance, 2026, minutes')
    await user.click(saveTagsBtn)

    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-1', {
        tags: ['governance', '2026', 'minutes'],
      }),
    )
  })

  it('renders version history and triggers download', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'versions')

    expect(screen.getByText('v1')).toBeInTheDocument()
    expect(screen.getAllByText('v2')).toHaveLength(2) // in header badge and in list
    expect(screen.getByText('current')).toBeInTheDocument()

    const downloadButtons = screen.getAllByRole('button', { name: 'Download' })
    expect(downloadButtons).toHaveLength(2)

    // Download version 2 (first in sorted list)
    await user.click(downloadButtons[0])
    await waitFor(() =>
      expect(docvaultApi.downloadDocument).toHaveBeenCalledWith('doc-1', 'v-2'),
    )
    expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob), 'minutes_final.pdf')
  })

  it('handles uploading a new version', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'versions')

    const file = new File(['new content'], 'minutes_v3.pdf', { type: 'application/pdf' })
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).toBeInTheDocument()

    await user.upload(fileInput, file)

    await waitFor(() => expect(docvaultApi.uploadVersion).toHaveBeenCalledTimes(1))
    const [docId, formData] = (docvaultApi.uploadVersion as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(docId).toBe('doc-1')
    expect(formData.get('file')).toBeInstanceOf(File)
  })

  it('handles archive confirmation flow when document is live', async () => {
    const user = userEvent.setup()
    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={mockDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    const archiveBtn = screen.getByRole('button', { name: 'Archive document' })
    await user.click(archiveBtn)

    const dialog = await screen.findByRole('dialog', { name: 'Archive document?' })
    expect(dialog).toBeInTheDocument()

    const confirmBtn = within(dialog).getByRole('button', { name: 'Archive' })
    await user.click(confirmBtn)

    await waitFor(() => expect(docvaultApi.deleteDocument).toHaveBeenCalledWith('doc-1'))
  })

  it('renders restore button and locked state when document is archived', async () => {
    const user = userEvent.setup()
    const archivedDoc: DocumentResponse = {
      ...mockDoc,
      status: 'archived',
      is_editable: false,
    }

    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={archivedDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    // Shows archived notice for status (Edit tab)
    await goToTab(user, 'edit')
    expect(screen.getByText('Archived documents are locked.')).toBeInTheDocument()

    // Upload dropzone is disabled / shows archived text (Versions tab)
    await goToTab(user, 'versions')
    expect(screen.getByText('Archived — new versions are disabled.')).toBeInTheDocument()

    // Restore button is present
    const restoreBtn = screen.getByRole('button', { name: 'Restore document' })
    await user.click(restoreBtn)

    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-1', {
        status: 'uploaded',
        is_editable: true,
      }),
    )
  })

  it('disables editing inputs and new version dropzone when document is locked (not editable)', async () => {
    const user = userEvent.setup()
    const lockedDoc: DocumentResponse = {
      ...mockDoc,
      is_editable: false,
    }

    renderComponent(
      <GraphDocumentInspector
        open={true}
        document={lockedDoc}
        buckets={mockBuckets}
        onClose={vi.fn()}
      />,
    )

    await goToTab(user, 'edit')

    const titleInput = screen.getByDisplayValue('Q3 Board Minutes')
    expect(titleInput).toBeDisabled()

    const tagsInput = screen.getByDisplayValue('board, minutes')
    expect(tagsInput).toBeDisabled()

    await goToTab(user, 'versions')
    expect(
      screen.getByText('This document is locked (new versions not allowed).'),
    ).toBeInTheDocument()
  })

  it('defaults to Overview tab showing read-only facts and tag chips', () => {
    renderComponent(<GraphDocumentInspector open document={mockDoc} buckets={mockBuckets} onClose={vi.fn()} />)
    expect(screen.getByTestId('inspector-tab-overview').getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('board')).toBeInTheDocument()
    expect(screen.getByText('minutes')).toBeInTheDocument()
    expect(screen.queryByDisplayValue('Q3 Board Minutes')).not.toBeInTheDocument()
  })

  it('switches tabs and resets to Overview when document changes', async () => {
    const user = userEvent.setup()
    const { rerender } = renderComponent(<GraphDocumentInspector open document={mockDoc} buckets={mockBuckets} onClose={vi.fn()} />)
    await user.click(screen.getByTestId('inspector-tab-edit'))
    expect(screen.getByTestId('inspector-tab-edit').getAttribute('aria-selected')).toBe('true')
    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
        <ToastProvider>
          <GraphDocumentInspector open document={{ ...mockDoc, id: 'doc-2' }} buckets={mockBuckets} onClose={vi.fn()} />
        </ToastProvider>
      </QueryClientProvider>,
    )
    expect(screen.getByTestId('inspector-tab-overview').getAttribute('aria-selected')).toBe('true')
  })
})
