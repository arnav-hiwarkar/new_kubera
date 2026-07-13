import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { CustomFieldsPage } from './CustomFieldsPage'
import type { CustomFieldResponse } from '@/api/types'
import { customFieldsApi } from '@/api/endpoints/customFields'

const authState = vi.hoisted(() => ({
  profile: { id: 'u1', role: 'admin', full_name: 'Admin' } as {
    id: string
    role: string
    full_name: string
  } | null,
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({
    profile: authState.profile,
    status: 'authenticated',
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}))
vi.mock('@/api/endpoints/customFields', () => ({
  customFieldsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    deactivate: vi.fn(),
    reactivate: vi.fn(),
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

function field(over: Partial<CustomFieldResponse>): CustomFieldResponse {
  return {
    id: 'f1',
    module: 'asset_management',
    field_name: 'Serial number',
    field_key: 'serial_number',
    field_type: 'text',
    is_required: false,
    dropdown_options: null,
    display_order: 0,
    is_active: true,
    company_id: 'co',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  authState.profile = { id: 'u1', role: 'admin', full_name: 'Admin' }
})

describe('CustomFieldsPage', () => {
  it('renders active and inactive fields with their statuses', async () => {
    vi.mocked(customFieldsApi.list).mockResolvedValue([
      field({ id: 'f1', field_name: 'Serial number', is_active: true }),
      field({ id: 'f2', field_name: 'Retired tag', field_key: 'retired_tag', is_active: false }),
    ])
    wrap(<CustomFieldsPage />)

    expect(await screen.findByText('Serial number')).toBeInTheDocument()
    expect(screen.getByText('Retired tag')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('Archived')).toBeInTheDocument()
  })

  it('creates a field via the New Field modal', async () => {
    vi.mocked(customFieldsApi.list).mockResolvedValue([])
    vi.mocked(customFieldsApi.create).mockResolvedValue(field({}))
    const u = userEvent.setup()
    wrap(<CustomFieldsPage />)

    await u.click(await screen.findByRole('button', { name: 'New Field' }))
    await u.type(screen.getByPlaceholderText('e.g. Serial number'), 'Warranty months')
    await u.selectOptions(screen.getByRole('combobox'), 'number')
    await u.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() =>
      expect(customFieldsApi.create).toHaveBeenCalledWith(
        'asset_management',
        expect.objectContaining({
          field_name: 'Warranty months',
          field_key: 'warranty_months',
          field_type: 'number',
        }),
      ),
    )
  })

  it('deactivates an active field and reactivates an inactive field', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(customFieldsApi.list).mockResolvedValue([
      field({ id: 'f1', field_name: 'Serial number', is_active: true }),
      field({ id: 'f2', field_name: 'Retired tag', field_key: 'retired_tag', is_active: false }),
    ])
    vi.mocked(customFieldsApi.deactivate).mockResolvedValue(field({ is_active: false }))
    vi.mocked(customFieldsApi.reactivate).mockResolvedValue(field({ is_active: true }))
    const u = userEvent.setup()
    wrap(<CustomFieldsPage />)

    await screen.findByText('Serial number')
    await u.click(screen.getByRole('button', { name: 'Deactivate' }))
    await waitFor(() =>
      expect(customFieldsApi.deactivate).toHaveBeenCalledWith('asset_management', 'f1'),
    )

    await u.click(screen.getByRole('button', { name: 'Reactivate' }))
    await waitFor(() =>
      expect(customFieldsApi.reactivate).toHaveBeenCalledWith('asset_management', 'f2'),
    )
  })
})
