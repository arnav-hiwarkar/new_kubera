import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { SalesPage } from './SalesPage'
import type { SalesRecordResponse, CustomFieldResponse, UserResponse } from '@/api/types'
import { salesApi } from '@/api/endpoints/sales'
import { usersApi } from '@/api/endpoints/users'
import { customFieldsApi } from '@/api/endpoints/customFields'

const authState = vi.hoisted(() => ({
  profile: null as { id: string; role: string; full_name: string } | null,
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: authState.profile, status: 'authenticated', signIn: vi.fn(), signOut: vi.fn() }),
}))
vi.mock('@/api/endpoints/sales', () => ({
  salesApi: {
    list: vi.fn(),
    aggregate: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    exportExcel: vi.fn(),
    inspectImport: vi.fn(),
    import: vi.fn(),
  },
}))
vi.mock('@/api/endpoints/users', () => ({
  usersApi: { list: vi.fn().mockResolvedValue([]), myReports: vi.fn().mockResolvedValue([]) },
}))
vi.mock('@/api/endpoints/customFields', () => ({ customFieldsApi: { list: vi.fn() } }))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
}

function sale(over: Partial<SalesRecordResponse> = {}): SalesRecordResponse {
  return {
    id: 's1',
    company_id: 'co',
    client_name: 'Acme Corp',
    product_service: 'Annual license',
    amount: 5000,
    status: 'lead',
    closing_date: '2026-08-01',
    user_id: 'emp',
    custom_fields: { region: 'West' },
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

const regionField: CustomFieldResponse = {
  id: 'f1',
  module: 'sales_tracking',
  field_name: 'Region',
  field_key: 'region',
  field_type: 'text',
  is_required: false,
  dropdown_options: null,
  display_order: 0,
  is_active: true,
  company_id: 'co',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
}

function user(over: Partial<UserResponse> = {}): UserResponse {
  return {
    id: 'u-1',
    email: 'user@example.com',
    full_name: 'Regular User',
    role: 'employee',
    manager_id: null,
    designation: null,
    department: null,
    is_active: true,
    accessible_modules: [],
    company_id: 'c-1',
    created_at: new Date().toISOString(),
    ...over,
  } as UserResponse
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(salesApi.list).mockResolvedValue([sale()])
  vi.mocked(salesApi.aggregate).mockResolvedValue([{ status: 'lead', total_amount: 5000, count: 1 }])
  vi.mocked(customFieldsApi.list).mockResolvedValue([regionField])
})

describe('SalesPage — employee', () => {
  beforeEach(() => {
    authState.profile = { id: 'emp', role: 'employee', full_name: 'Emp' }
  })

  it('renders the sales list + summary cards and shows New/Import/Export for everyone', async () => {
    wrap(<SalesPage />)

    expect(await screen.findByText('Acme Corp')).toBeInTheDocument()
    // Summary cards: one per SALES_STATUS, sourced from the aggregate row.
    expect(screen.getAllByText('Lead').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Won').length).toBeGreaterThan(0)
    // The aggregate row's total amount renders on the Lead card.
    expect(screen.getAllByText('5,000.00').length).toBeGreaterThan(0)

    expect(screen.getByRole('button', { name: 'New sale' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument()
  })

  it('opens the create form with a custom field but no owner picker for an employee', async () => {
    const u = userEvent.setup()
    wrap(<SalesPage />)

    await screen.findByText('Acme Corp')
    await u.click(screen.getByRole('button', { name: 'New sale' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Region')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Create sale' })).toBeInTheDocument()
    // Employees never see the owner picker (the "Owner" column header still exists).
    expect(within(dialog).queryByText('Owner')).not.toBeInTheDocument()
  })
})

describe('SalesPage — manager', () => {
  beforeEach(() => {
    authState.profile = { id: 'mgr', role: 'manager', full_name: 'Manager' }
    vi.mocked(usersApi.myReports).mockResolvedValue([user()])
  })

  it('shows the owner picker in the create form', async () => {
    const u = userEvent.setup()
    wrap(<SalesPage />)

    await screen.findByText('Acme Corp')
    await u.click(screen.getByRole('button', { name: 'New sale' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Owner')).toBeInTheDocument()
  })
})
