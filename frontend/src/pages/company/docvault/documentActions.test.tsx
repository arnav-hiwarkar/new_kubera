/**
 * The hook's job is to call the *right endpoint*. Bug A was two actions calling
 * PATCH with a `status` field the server forbids, so these tests assert the
 * endpoint and body of every mutation.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { useDocumentActions } from './useDocumentActions'
import { docvaultApi } from '@/api/endpoints/docvault'
import type { DocumentResponse } from '@/api/types'

const authState = vi.hoisted(() => ({
  profile: null as { id: string; role: string } | null,
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: authState.profile, status: 'authenticated' }),
}))

vi.mock('@/api/endpoints/docvault', () => ({
  docvaultApi: {
    updateDocument: vi.fn().mockResolvedValue({}),
    reviewDocument: vi.fn().mockResolvedValue({}),
    requestApproval: vi.fn().mockResolvedValue({}),
    deleteDocument: vi.fn().mockResolvedValue(undefined),
    restoreDocument: vi.fn().mockResolvedValue({}),
    uploadVersion: vi.fn().mockResolvedValue({}),
    downloadDocument: vi.fn().mockResolvedValue(new Blob()),
    listDocuments: vi.fn().mockResolvedValue([]),
  },
}))
vi.mock('@/lib/download', () => ({ saveBlob: vi.fn() }))

const DOC = {
  id: 'doc-1',
  company_id: 'co-1',
  title: 'Minutes',
  status: 'archived',
  bucket_id: 'bucket-1',
  doc_type_id: null,
  tags: [],
  is_editable: false,
  created_by: 'u-creator',
  approver_id: 'u-approver',
  current_version_id: 'v-1',
  versions: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as unknown as DocumentResponse

/** Minimal probe so we can drive the hook without a full component. */
function Probe({ document }: { document: DocumentResponse }) {
  const a = useDocumentActions(document)
  return (
    <div>
      <button onClick={() => void a.restore()}>restore</button>
      <button onClick={() => void a.doArchive()}>archive</button>
      <button onClick={() => void a.handleApprove()}>approve</button>
      <span data-testid="can-restore">{String(a.canRestore)}</span>
    </div>
  )
}

function wrap(document: DocumentResponse) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <Probe document={document} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('useDocumentActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.profile = { id: 'u-admin', role: 'admin' }
  })

  it('restores through the restore endpoint, never through PATCH', async () => {
    // This is Bug A: restore used to PATCH {status:'uploaded', is_editable:true},
    // which DocumentUpdate forbids (extra="forbid"), so it 422'd.
    const u = userEvent.setup()
    wrap(DOC)
    await u.click(screen.getByText('restore'))
    await waitFor(() => expect(docvaultApi.restoreDocument).toHaveBeenCalledWith('doc-1'))
    expect(docvaultApi.updateDocument).not.toHaveBeenCalled()
  })

  it('archives through the DELETE endpoint', async () => {
    const u = userEvent.setup()
    wrap({ ...DOC, status: 'uploaded', is_editable: true } as DocumentResponse)
    await u.click(screen.getByText('archive'))
    await waitFor(() => expect(docvaultApi.deleteDocument).toHaveBeenCalledWith('doc-1'))
    expect(docvaultApi.updateDocument).not.toHaveBeenCalled()
  })

  it('approves through the review endpoint with a decision, not a status', async () => {
    const u = userEvent.setup()
    wrap({ ...DOC, status: 'pending_approval', is_editable: true } as DocumentResponse)
    await u.click(screen.getByText('approve'))
    await waitFor(() =>
      expect(docvaultApi.reviewDocument).toHaveBeenCalledWith('doc-1', {
        decision: 'verified',
        approval_notes: undefined,
      }),
    )
    expect(docvaultApi.updateDocument).not.toHaveBeenCalled()
  })

  it('exposes the permission flags alongside the handlers', async () => {
    wrap(DOC)
    expect(screen.getByTestId('can-restore').textContent).toBe('true')
  })

  it('withholds restore from a non-admin', async () => {
    authState.profile = { id: 'u-creator', role: 'employee' }
    wrap(DOC)
    expect(screen.getByTestId('can-restore').textContent).toBe('false')
  })
})
