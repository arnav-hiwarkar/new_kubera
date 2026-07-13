import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { AssetsPage } from './AssetsPage'
import type { AssetResponse, CustomFieldResponse } from '@/api/types'
import { assetsApi } from '@/api/endpoints/assets'
import { customFieldsApi } from '@/api/endpoints/customFields'

const authState = vi.hoisted(() => ({
  profile: null as { id: string; role: string; full_name: string } | null,
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: authState.profile, status: 'authenticated', signIn: vi.fn(), signOut: vi.fn() }),
}))
vi.mock('@/api/endpoints/assets', () => ({
  assetsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    exportExcel: vi.fn(),
    inspectImport: vi.fn(),
    import: vi.fn(),
  },
}))
vi.mock('@/api/endpoints/users', () => ({ usersApi: { list: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/api/endpoints/docvault', () => ({ docvaultApi: { listDocuments: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/api/endpoints/customFields', () => ({ customFieldsApi: { list: vi.fn() } }))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
}

function asset(over: Partial<AssetResponse> = {}): AssetResponse {
  return {
    id: 'a1',
    company_id: 'co',
    asset_name: 'MacBook Pro',
    serial_number: 'SN-1',
    category: 'hardware',
    status: 'active',
    purchase_date: '2024-03-15',
    purchase_cost: 1200,
    depreciation_rate: null,
    custodian_id: null,
    document_id: null,
    custom_fields: { warranty: '1yr' },
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

const warrantyField: CustomFieldResponse = {
  id: 'f1',
  module: 'asset_management',
  field_name: 'Warranty',
  field_key: 'warranty',
  field_type: 'text',
  is_required: false,
  dropdown_options: null,
  display_order: 0,
  is_active: true,
  company_id: 'co',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(assetsApi.list).mockResolvedValue([asset()])
  vi.mocked(customFieldsApi.list).mockResolvedValue([warrantyField])
})

describe('AssetsPage — admin', () => {
  beforeEach(() => {
    authState.profile = { id: 'admin', role: 'admin', full_name: 'Admin' }
  })

  it('shows admin actions and renders custom fields in the create drawer', async () => {
    const u = userEvent.setup()
    wrap(<AssetsPage />)

    expect(await screen.findByText('MacBook Pro')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New asset' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'New asset' }))
    // The dynamic custom field renders in the drawer.
    expect(await screen.findByText('Warranty')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create asset' })).toBeInTheDocument()
  })
})

describe('AssetsPage — non-admin', () => {
  beforeEach(() => {
    authState.profile = { id: 'emp', role: 'employee', full_name: 'Emp' }
  })

  it('hides admin actions and opens a read-only drawer', async () => {
    const u = userEvent.setup()
    wrap(<AssetsPage />)

    expect(await screen.findByText('MacBook Pro')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New asset' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Import' })).not.toBeInTheDocument()

    await u.click(screen.getByText('MacBook Pro'))
    // Read-only drawer renders labelled values (not editable inputs) and no
    // Save/Create action. "Serial number" only appears inside the drawer.
    expect(await screen.findByText('Serial number')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create asset' })).not.toBeInTheDocument()
  })
})
