import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { MemoryRouter } from 'react-router-dom'
import { UploadDocumentModal } from './UploadDocumentModal'
import { DocumentDrawer } from './DocumentDrawer'
import { DocVaultPage } from './DocVaultPage'
import { Dashboard } from '@/pages/company/Dashboard'
import type { DocumentResponse, UserResponse } from '@/api/types'
import { docvaultApi } from '@/api/endpoints/docvault'
import { usersApi } from '@/api/endpoints/users'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({
    profile: {
      id: 'u-approver-1',
      role: 'employee',
      email: 'approver@acme.test',
      full_name: 'Approver Alice',
      accessible_modules: ['dashboard', 'docvault'],
    },
    status: 'authenticated',
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
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

vi.mock('@/api/endpoints/users', () => ({
  usersApi: {
    list: vi.fn().mockResolvedValue([
      {
        id: 'u-approver-1',
        full_name: 'Approver Alice',
        email: 'approver@acme.test',
        role: 'employee',
        accessible_modules: ['docvault'],
        is_active: true,
      },
      {
        id: 'u-approver-2',
        full_name: 'Bob Manager',
        email: 'bob@acme.test',
        role: 'admin',
        accessible_modules: ['docvault'],
        is_active: true,
      },
    ] as UserResponse[]),
    me: vi.fn().mockResolvedValue({}),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

const baseDoc: DocumentResponse = {
  id: 'doc-100',
  company_id: 'co-1',
  current_version_id: 'v-1',
  bucket_id: null,
  status: 'pending_approval',
  title: 'Annual Audit 2026',
  doc_type_id: null,
  tags: ['audit', 'finance'],
  is_editable: false, // Final
  created_by: 'u-uploader-1',
  created_by_name: 'Charlie Creator',
  approver_id: 'u-approver-1',
  approver_name: 'Approver Alice',
  approval_requested_at: '2026-08-28T10:00:00Z',
  created_at: '2026-08-28T10:00:00Z',
  updated_at: '2026-08-28T10:00:00Z',
  versions: [
    {
      id: 'v-1',
      document_id: 'doc-100',
      original_filename: 'audit.pdf',
      mime_type: 'application/pdf',
      size_bytes: 5400,
      checksum: 'xyz',
      uploaded_by: 'u-uploader-1',
      uploaded_by_name: 'Charlie Creator',
      uploaded_at: '2026-08-28T10:00:00Z',
      version_number: 1,
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DocVault Approvals & Final Status', () => {
  it('submits approval request and Final lock from UploadDocumentModal', async () => {
    const user = userEvent.setup()
    wrap(<UploadDocumentModal open onClose={() => {}} buckets={[]} />)

    const file = new File(['test content'], 'audit_report.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    // Check request approval checkbox
    const approvalCheckbox = screen.getByLabelText(/Request document approval/i)
    await user.click(approvalCheckbox)

    // ApproverPicker appears -> select Bob Manager
    const approverTrigger = await screen.findByRole('button', { name: /Select an approver/i })
    await user.click(approverTrigger)

    const bobOption = await screen.findByText('Bob Manager')
    await user.click(bobOption)

    // Toggle Mark as Final
    const finalCheckbox = screen.getByLabelText(/Mark as Final/i)
    await user.click(finalCheckbox)

    // Submit upload
    const uploadBtn = screen.getByRole('button', { name: /Upload & Request Approval/i })
    await user.click(uploadBtn)

    await waitFor(() => expect(docvaultApi.uploadDocument).toHaveBeenCalledTimes(1))
    const fd = (docvaultApi.uploadDocument as ReturnType<typeof vi.fn>).mock.calls[0][0] as FormData
    expect(fd.get('title')).toBe('audit_report')
    expect(fd.get('needs_approval')).toBe('true')
    expect(fd.get('approver_id')).toBe('u-approver-2')
    expect(fd.get('is_editable')).toBe('false')
  })

  it('renders Final badge and Review & Approve hover trigger in DocVaultPage', async () => {
    vi.mocked(docvaultApi.listDocuments).mockResolvedValueOnce([baseDoc])

    wrap(<DocVaultPage />)

    // Title and Final badge
    expect(await screen.findByText('Annual Audit 2026')).toBeInTheDocument()
    expect(screen.getByText('Final')).toBeInTheDocument()

    // Needs your review status note
    expect(screen.getByText('Needs your review')).toBeInTheDocument()

    // Review & Approve button for assigned approver
    expect(screen.getByRole('button', { name: /Review & Approve/i })).toBeInTheDocument()
  })

  it('handles Approve action in DocumentDrawer', async () => {
    const user = userEvent.setup()
    wrap(<DocumentDrawer document={baseDoc} open onClose={() => {}} buckets={[]} />)

    expect(screen.getByText(/Review & Approval Required/i)).toBeInTheDocument()
    expect(screen.getByText(/Requested by Charlie Creator/i)).toBeInTheDocument()

    const notesInput = screen.getByLabelText(/Review notes/i)
    await user.type(notesInput, 'All figures match ledger accounts')

    const approveBtn = screen.getByRole('button', { name: /Approve \(Verified\)/i })
    await user.click(approveBtn)

    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-100', {
        status: 'verified',
        approval_notes: 'All figures match ledger accounts',
      }),
    )
  })

  it('handles Request Changes action in DocumentDrawer', async () => {
    const user = userEvent.setup()
    wrap(<DocumentDrawer document={baseDoc} open onClose={() => {}} buckets={[]} />)

    const notesInput = screen.getByLabelText(/Review notes/i)
    await user.type(notesInput, 'Please attach appendix B')

    const requestChangesBtn = screen.getByRole('button', { name: /Request Changes/i })
    await user.click(requestChangesBtn)

    await waitFor(() =>
      expect(docvaultApi.updateDocument).toHaveBeenCalledWith('doc-100', {
        status: 'action_required',
        approval_notes: 'Please attach appendix B',
      }),
    )
  })

  it('renders Pending Approvals card on company Dashboard', async () => {
    vi.mocked(docvaultApi.listDocuments).mockResolvedValueOnce([baseDoc])

    wrap(<Dashboard />)

    expect(await screen.findByText(/Documents Pending Your Approval/i)).toBeInTheDocument()
    expect(screen.getByText('Annual Audit 2026')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Review & Approve/i })).toBeInTheDocument()
  })
})
