import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { UploadDocumentModal } from './UploadDocumentModal'
import { DocumentDrawer } from './DocumentDrawer'
import type { DocumentResponse } from '@/api/types'
import { docvaultApi } from '@/api/endpoints/docvault'

// Mock the API client layer — tests assert the module calls it correctly,
// not the network itself.
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

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
}

const doc: DocumentResponse = {
  id: 'doc-1',
  company_id: 'co-1',
  current_version_id: 'v-1',
  bucket_id: null,
  status: 'uploaded',
  title: 'Q3 Board Minutes',
  doc_type_id: null,
  tags: ['board'],
  is_editable: true,
  created_by: 'u-1',
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-01T00:00:00Z',
  versions: [
    {
      id: 'v-1',
      document_id: 'doc-1',
      original_filename: 'minutes.pdf',
      mime_type: 'application/pdf',
      size_bytes: 2100,
      checksum: 'abc',
      uploaded_by: 'u-1',
      uploaded_at: '2026-06-01T00:00:00Z',
      version_number: 1,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('UploadDocumentModal', () => {
  it('sends title + file as FormData on upload', async () => {
    const user = userEvent.setup()
    wrap(<UploadDocumentModal open onClose={() => {}} buckets={[]} />)

    const file = new File(['hello'], 'report.pdf', { type: 'application/pdf' })
    // The dropzone renders a hidden file input.
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    // Title auto-fills from the filename.
    expect(await screen.findByDisplayValue('report')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Upload' }))

    await waitFor(() => expect(docvaultApi.uploadDocument).toHaveBeenCalledTimes(1))
    const fd = (docvaultApi.uploadDocument as ReturnType<typeof vi.fn>).mock.calls[0][0] as FormData
    expect(fd.get('title')).toBe('report')
    expect(fd.get('file')).toBeInstanceOf(File)
    expect(fd.get('is_editable')).toBe('true')
  })
})

describe('DocumentDrawer archive flow', () => {
  it('archives via DELETE after confirming', async () => {
    const user = userEvent.setup()
    wrap(<DocumentDrawer document={doc} open onClose={() => {}} buckets={[]} />)

    await user.click(screen.getByRole('button', { name: 'Archive' }))

    // ConfirmDialog appears; confirm it.
    const dialog = await screen.findByRole('dialog', { name: 'Archive document?' })
    await user.click(within(dialog).getByRole('button', { name: 'Archive' }))

    await waitFor(() => expect(docvaultApi.deleteDocument).toHaveBeenCalledWith('doc-1'))
  })
})
