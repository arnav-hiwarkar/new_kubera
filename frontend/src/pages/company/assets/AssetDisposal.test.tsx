/**
 * KUB-020 front-end coverage. The server is the authorization boundary here —
 * these tests pin the two things the browser is still responsible for: not
 * offering an action the caller cannot perform, and failing legibly when the
 * server refuses one anyway (stale profile, role changed mid-session).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui/Toast'
import { AssetDetailPage } from './AssetDetailPage'
import { AssetDisposalModal } from './AssetDisposalModal'
import { assetsApi } from '@/api/endpoints/assets'
import { ApiError } from '@/api/http'
import type { AssetDetailResponse } from '@/api/types'

const authState = vi.hoisted(() => ({
  profile: null as { id: string; role: string; full_name: string } | null,
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({
    profile: authState.profile,
    status: 'authenticated',
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}))
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('@/api/endpoints/assets', () => ({
  assetsApi: {
    get: vi.fn(),
    list: vi.fn().mockResolvedValue([]),
    update: vi.fn(),
    submit: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    dispose: vi.fn(),
    remove: vi.fn(),
    costPreview: vi.fn(),
    assignSerials: vi.fn(),
    listDocuments: vi.fn().mockResolvedValue([]),
    uploadDocument: vi.fn(),
    uploadAcquisitionDocument: vi.fn(),
    detachDocument: vi.fn(),
    documentBlob: vi.fn(),
  },
  acquisitionsApi: { list: vi.fn(), get: vi.fn(), units: vi.fn(), update: vi.fn() },
  ACQUISITION_DOC_ROLES: [],
  PHOTO_DOC_ROLES: [],
}))
vi.mock('@/api/endpoints/assetMasters', () => ({
  assetMastersApi: {
    listCategories: vi.fn().mockResolvedValue([]),
    listSuppliers: vi.fn().mockResolvedValue([]),
    listLookups: vi.fn().mockResolvedValue([]),
    listItBlocks: vi.fn().mockResolvedValue([]),
  },
}))
vi.mock('@/api/endpoints/users', () => ({ usersApi: { list: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/api/endpoints/activity', () => ({ activityApi: { list: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/api/endpoints/customFields', () => ({
  customFieldsApi: { list: vi.fn().mockResolvedValue([]) },
}))

const CAPITALIZED_DETAIL = {
  asset: {
    id: 'a1',
    asset_name: 'Rack Server',
    asset_code: 'SRV-000001',
    lifecycle_status: 'capitalized',
    operational_status: 'in_use',
    capitalization_date: '2026-04-10',
    available_for_use_date: '2026-04-10',
    original_cost: '500000.00',
    category_id: 'cat-leaf',
  },
  acquisition: null,
  siblings: [],
  documents: [],
  blocking_issues: [],
} as unknown as AssetDetailResponse

function wrapDetail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/app/assets/a1']}>
          <Routes>
            <Route path="/app/assets/:assetId" element={<AssetDetailPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('AssetDetailPage — dispose button gating', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(assetsApi.get).mockResolvedValue(CAPITALIZED_DETAIL)
  })

  it('offers disposal to an admin on a capitalized asset', async () => {
    authState.profile = { id: 'u-admin', role: 'admin', full_name: 'Admin' }
    wrapDetail()
    expect(await screen.findByText('On the books')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dispose Asset' })).toBeInTheDocument()
  })

  it('does not offer disposal to an employee', async () => {
    authState.profile = { id: 'u-emp', role: 'employee', full_name: 'Employee' }
    wrapDetail()
    expect(await screen.findByText('On the books')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dispose Asset' })).not.toBeInTheDocument()
  })

  it('does not offer disposal for the removed `manager` role (KUB-018 drift)', async () => {
    authState.profile = { id: 'u-mgr', role: 'manager', full_name: 'Manager' }
    wrapDetail()
    expect(await screen.findByText('On the books')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dispose Asset' })).not.toBeInTheDocument()
  })
})

function wrapModal(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(qc, 'invalidateQueries')
  const utils = render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <AssetDisposalModal
          open
          onClose={onClose}
          assetId="a1"
          assetName="Rack Server"
          capitalizationDate="2026-04-10"
        />
      </ToastProvider>
    </QueryClientProvider>,
  )
  return { ...utils, onClose, invalidate }
}

describe('AssetDisposalModal — server refusal handling', () => {
  beforeEach(() => vi.clearAllMocks())

  it('closes and explains when the server refuses with 403', async () => {
    const u = userEvent.setup()
    vi.mocked(assetsApi.dispose).mockRejectedValue(
      new ApiError(403, 'Insufficient permissions'),
    )
    const { onClose } = wrapModal()

    await u.click(screen.getByRole('button', { name: /confirm disposal/i }))

    expect(await screen.findByText(/do not have permission to dispose/i)).toBeInTheDocument()
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('closes and refreshes when the asset was already disposed (409)', async () => {
    const u = userEvent.setup()
    vi.mocked(assetsApi.dispose).mockRejectedValue(
      new ApiError(409, 'Only a capitalized asset can be disposed of (this asset is disposed)'),
    )
    const { onClose, invalidate } = wrapModal()

    await u.click(screen.getByRole('button', { name: /confirm disposal/i }))

    expect(
      await screen.findByText(/only a capitalized asset can be disposed of/i),
    ).toBeInTheDocument()
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['asset', 'a1'] })
  })

  it('keeps the form open for a recoverable validation error', async () => {
    const u = userEvent.setup()
    vi.mocked(assetsApi.dispose).mockRejectedValue(
      new ApiError(422, 'Sale proceeds are required for a sale'),
    )
    const { onClose } = wrapModal()

    await u.click(screen.getByRole('button', { name: /confirm disposal/i }))

    expect(await screen.findByText(/sale proceeds are required/i)).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})
