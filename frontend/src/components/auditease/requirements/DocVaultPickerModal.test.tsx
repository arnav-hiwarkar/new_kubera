import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DocVaultPickerModal } from './DocVaultPickerModal'
import { docvaultApi } from '@/api/endpoints/docvault'

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('DocVaultPickerModal', () => {
  const mockBuckets = [
    {
      id: 'b-1',
      name: 'Financial Statements',
      company_id: 'co-1',
      created_by: null,
      visibility: 'everyone' as const,
      access_user_ids: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'b-2',
      name: 'Tax Documents',
      company_id: 'co-1',
      created_by: null,
      visibility: 'everyone' as const,
      access_user_ids: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ]

  const mockDocs = [
    {
      id: 'doc-1',
      company_id: 'co-1',
      bucket_id: 'b-1',
      doc_type_id: null,
      title: 'P&L FY24 Statement',
      tags: ['pnl', 'audit'],
      status: 'uploaded' as const,
      is_editable: false,
      created_by: 'u-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      current_version_id: 'v-1',
      versions: [
        {
          id: 'v-1',
          document_id: 'doc-1',
          version_number: 1,
          original_filename: 'pnl_2024.pdf',
          size_bytes: 50000,
          mime_type: 'application/pdf',
          uploaded_by: 'u-1',
          uploaded_at: '2026-01-01T00:00:00Z',
          checksum: 'abc1',
        },
      ],
    },
    {
      id: 'doc-2',
      company_id: 'co-1',
      bucket_id: 'b-2',
      doc_type_id: null,
      title: 'Form 16 Tax Return',
      tags: ['tax'],
      status: 'uploaded' as const,
      is_editable: false,
      created_by: 'u-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      current_version_id: 'v-2',
      versions: [
        {
          id: 'v-2',
          document_id: 'doc-2',
          version_number: 1,
          original_filename: 'form16.pdf',
          size_bytes: 30000,
          mime_type: 'application/pdf',
          uploaded_by: 'u-1',
          uploaded_at: '2026-01-01T00:00:00Z',
          checksum: 'abc2',
        },
      ],
    },
  ]

  it('renders modal with documents and buckets in rail', async () => {
    vi.spyOn(docvaultApi, 'listBuckets').mockResolvedValue(mockBuckets)
    vi.spyOn(docvaultApi, 'listDocuments').mockResolvedValue(mockDocs)

    renderWithClient(
      <DocVaultPickerModal
        open
        onClose={vi.fn()}
        selectedDocIds={[]}
        onConfirm={vi.fn()}
      />
    )

    expect(screen.getByText('Select Documents from DocVault')).toBeInTheDocument()
    expect(await screen.findByText('P&L FY24 Statement')).toBeInTheDocument()
    expect(screen.getByText('Form 16 Tax Return')).toBeInTheDocument()
    expect(screen.getAllByText('Financial Statements').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('All Documents')).toBeInTheDocument()
  })

  it('filters documents when searching across title, tag, or filename', async () => {
    vi.spyOn(docvaultApi, 'listBuckets').mockResolvedValue(mockBuckets)
    vi.spyOn(docvaultApi, 'listDocuments').mockResolvedValue(mockDocs)

    renderWithClient(
      <DocVaultPickerModal
        open
        onClose={vi.fn()}
        selectedDocIds={[]}
        onConfirm={vi.fn()}
      />
    )

    expect(await screen.findByText('P&L FY24 Statement')).toBeInTheDocument()
    const searchInput = screen.getByPlaceholderText(/search across title/i)
    fireEvent.change(searchInput, { target: { value: 'form16.pdf' } })

    expect(screen.queryByText('P&L FY24 Statement')).not.toBeInTheDocument()
    expect(screen.getByText('Form 16 Tax Return')).toBeInTheDocument()
  })

  it('filters documents when clicking a bucket in the rail', async () => {
    vi.spyOn(docvaultApi, 'listBuckets').mockResolvedValue(mockBuckets)
    vi.spyOn(docvaultApi, 'listDocuments').mockResolvedValue(mockDocs)

    renderWithClient(
      <DocVaultPickerModal
        open
        onClose={vi.fn()}
        selectedDocIds={[]}
        onConfirm={vi.fn()}
      />
    )

    expect(await screen.findByText('P&L FY24 Statement')).toBeInTheDocument()
    const bucketBtn = screen.getByRole('button', { name: /Tax Documents/i })
    fireEvent.click(bucketBtn)

    expect(screen.queryByText('P&L FY24 Statement')).not.toBeInTheDocument()
    expect(screen.getByText('Form 16 Tax Return')).toBeInTheDocument()
  })

  it('filters documents by clicking tag pills', async () => {
    vi.spyOn(docvaultApi, 'listBuckets').mockResolvedValue(mockBuckets)
    vi.spyOn(docvaultApi, 'listDocuments').mockResolvedValue(mockDocs)

    renderWithClient(
      <DocVaultPickerModal
        open
        onClose={vi.fn()}
        selectedDocIds={[]}
        onConfirm={vi.fn()}
      />
    )

    expect(await screen.findByText('P&L FY24 Statement')).toBeInTheDocument()
    const tagBtn = screen.getByRole('button', { name: '#tax' })
    fireEvent.click(tagBtn)

    expect(screen.queryByText('P&L FY24 Statement')).not.toBeInTheDocument()
    expect(screen.getByText('Form 16 Tax Return')).toBeInTheDocument()
  })

  it('toggles selection and confirms picked documents', async () => {
    vi.spyOn(docvaultApi, 'listBuckets').mockResolvedValue(mockBuckets)
    vi.spyOn(docvaultApi, 'listDocuments').mockResolvedValue(mockDocs)
    const onConfirm = vi.fn()
    const onClose = vi.fn()

    renderWithClient(
      <DocVaultPickerModal
        open
        onClose={onClose}
        selectedDocIds={[]}
        onConfirm={onConfirm}
      />
    )

    const docItem = await screen.findByText('P&L FY24 Statement')
    fireEvent.click(docItem)

    const attachBtn = screen.getByRole('button', { name: /Attach Selected \(1\)/i })
    expect(attachBtn).toBeInTheDocument()
    fireEvent.click(attachBtn)

    expect(onConfirm).toHaveBeenCalledWith(['doc-1'])
    expect(onClose).toHaveBeenCalled()
  })

  it('supports selecting all visible documents and clearing selection', async () => {
    vi.spyOn(docvaultApi, 'listBuckets').mockResolvedValue(mockBuckets)
    vi.spyOn(docvaultApi, 'listDocuments').mockResolvedValue(mockDocs)

    renderWithClient(
      <DocVaultPickerModal
        open
        onClose={vi.fn()}
        selectedDocIds={[]}
        onConfirm={vi.fn()}
      />
    )

    expect(await screen.findByText('P&L FY24 Statement')).toBeInTheDocument()
    const selectAllBtn = screen.getByRole('button', { name: /Select all \(2\)/i })
    fireEvent.click(selectAllBtn)

    expect(screen.getByRole('button', { name: /Attach Selected \(2\)/i })).toBeInTheDocument()
    expect(screen.getByText('2 documents staged')).toBeInTheDocument()

    const clearAllBtn = screen.getByText('Clear all')
    fireEvent.click(clearAllBtn)

    expect(screen.queryByText('2 documents staged')).not.toBeInTheDocument()
  })
})
