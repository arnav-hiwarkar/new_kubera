import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui/Toast'
import { AssetsPage } from './AssetsPage'
import { AssetDetailPage } from './AssetDetailPage'
import { assetsApi } from '@/api/endpoints/assets'
import { assetMastersApi } from '@/api/endpoints/assetMasters'
import type {
  AcquisitionResponse,
  AssetCategoryResponse,
  AssetDetailResponse,
  AssetResponse,
} from '@/api/types'

const navigate = vi.hoisted(() => vi.fn())
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
  return { ...actual, useNavigate: () => navigate }
})
vi.mock('@/api/endpoints/assets', () => ({
  assetsApi: {
    list: vi.fn(),
    get: vi.fn(),
    quickAdd: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    submit: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    costPreview: vi.fn(),
    assignSerials: vi.fn(),
    exportExcel: vi.fn(),
    listDocuments: vi.fn().mockResolvedValue([]),
    uploadDocument: vi.fn(),
    uploadAcquisitionDocument: vi.fn(),
    detachDocument: vi.fn(),
    documentBlob: vi.fn(),
  },
  acquisitionsApi: { list: vi.fn(), get: vi.fn(), units: vi.fn(), update: vi.fn() },
  ACQUISITION_DOC_ROLES: [
    'invoice',
    'purchase_order',
    'grn',
    'eway_bill',
    'approval',
    'customs',
    'lease',
  ],
  PHOTO_DOC_ROLES: ['asset_photo', 'serial_photo'],
}))
vi.mock('@/api/endpoints/assetMasters', () => ({
  assetMastersApi: {
    listCategories: vi.fn(),
    createCategory: vi.fn(),
    updateCategory: vi.fn(),
    listItBlocks: vi.fn().mockResolvedValue([]),
    listSuppliers: vi.fn().mockResolvedValue([]),
    createSupplier: vi.fn(),
    updateSupplier: vi.fn(),
    listLookups: vi.fn().mockResolvedValue([]),
    createLookup: vi.fn(),
    updateLookup: vi.fn(),
  },
}))
vi.mock('@/api/endpoints/users', () => ({ usersApi: { list: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/api/endpoints/activity', () => ({ activityApi: { list: vi.fn().mockResolvedValue([]) } }))

function wrap(ui: React.ReactElement, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/" element={ui} />
            <Route path="/app/assets/:assetId" element={<AssetDetailPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

const LAPTOP_CATEGORY: AssetCategoryResponse = {
  id: 'cat-leaf',
  company_id: null,
  parent_id: 'cat-parent',
  name: 'End user devices (desktops, laptops, printers)',
  code: null,
  default_useful_life_months: 36,
  default_dep_method: 'slm',
  default_residual_pct: 5,
  default_it_block_id: 'blk1',
  default_it_block_code: 'PM-40-COMP',
  default_it_block_rate: 40,
  default_itc_treatment: null,
  tag_prefix: 'COMP',
  applicable_field_groups: ['network_ids'],
  schedule_ii_reference: 'Part C 5(b)',
  is_active: true,
  display_order: 20,
}

const PARENT_CATEGORY: AssetCategoryResponse = {
  ...LAPTOP_CATEGORY,
  id: 'cat-parent',
  parent_id: null,
  name: 'Computers and data processing units',
  default_useful_life_months: null,
  default_dep_method: null,
  default_residual_pct: null,
  applicable_field_groups: [],
}

function assetRow(over: Partial<AssetResponse> = {}): AssetResponse {
  return {
    id: 'a1',
    company_id: 'co',
    acquisition_id: 'acq1',
    unit_index: 1,
    asset_code: 'COMP-000001',
    asset_name: 'MacBook Pro',
    category_id: 'cat-leaf',
    description: null,
    manufacturer: null,
    manufacturer_contact: null,
    brand_model: null,
    manufacturer_serial_number: 'SN-1',
    lifecycle_status: 'draft',
    operational_status: null,
    condition: null,
    branch_id: null,
    cost_centre_id: null,
    department_id: null,
    location_id: null,
    custodian_id: null,
    custodian_name: null,
    custodian_employee_code: null,
    available_for_use_date: null,
    capitalization_date: null,
    warranty_start_date: null,
    warranty_months: null,
    warranty_expiry_date: null,
    useful_life_months: 36,
    dep_method: 'slm',
    residual_pct: '5.00',
    residual_value: null,
    useful_life_override_reason: null,
    it_block_id: 'blk1',
    it_dep_rate: '40.00',
    it_put_to_use_date: null,
    original_cost: '60000.00',
    is_pre_cutover: false,
    opening_accumulated_depreciation: null,
    opening_wdv: null,
    opening_it_wdv: null,
    registration_number: null,
    engine_number: null,
    chassis_number: null,
    imei: null,
    mac_address: null,
    technical_specs: null,
    remarks: null,
    parent_asset_id: null,
    custom_fields: {},
    created_by: 'admin',
    submitted_by: null,
    submitted_at: null,
    approved_by: null,
    approved_at: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

function acquisition(over: Partial<AcquisitionResponse> = {}): AcquisitionResponse {
  return {
    id: 'acq1',
    company_id: 'co',
    supplier_id: null,
    supplier_name_snapshot: 'Acme Ltd',
    supplier_gstin_snapshot: '27ABCDE1234F1Z5',
    invoice_number: null,
    invoice_date: null,
    po_number: null,
    purchase_date: null,
    quantity: 1,
    unit_basic_price: '60000.00',
    discount_type: 'amount',
    discount_value: null,
    hsn_sac_code: null,
    gst_rate: '18.00',
    branch_id: null,
    place_of_supply_state_code: '27',
    cgst_amount: '5400.00',
    sgst_amount: '5400.00',
    igst_amount: '0.00',
    gst_amounts_overridden: false,
    gst_split_basis: 'intra_state',
    itc_treatment: 'eligible',
    itc_eligible_pct: null,
    freight_cost: null,
    installation_cost: null,
    other_capitalizable_cost: null,
    gross_basic_price: '60000.00',
    discount_amount: '0.00',
    net_basic_price: '60000.00',
    total_gst: '10800.00',
    recoverable_gst: '10800.00',
    capitalizable_gst: '0.00',
    landed_cost: '60000.00',
    total_acquisition_outlay: '70800.00',
    per_unit_cost: '60000.00',
    is_imported: false,
    is_leased: false,
    grn_number: null,
    grn_date: null,
    delivery_challan_number: null,
    eway_bill_number: null,
    irn: null,
    bill_of_entry_number: null,
    bill_of_entry_date: null,
    customs_duty: null,
    foreign_currency: null,
    foreign_currency_value: null,
    exchange_rate: null,
    lease_type: null,
    lessor_name: null,
    lease_start_date: null,
    lease_end_date: null,
    lease_rental: null,
    project_budget_reference: null,
    remarks: null,
    created_by: 'admin',
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

function detail(over: Partial<AssetDetailResponse> = {}): AssetDetailResponse {
  return {
    asset: assetRow(),
    acquisition: acquisition(),
    siblings: [
      {
        id: 'a1',
        unit_index: 1,
        asset_code: 'COMP-000001',
        lifecycle_status: 'draft',
        manufacturer_serial_number: 'SN-1',
      },
    ],
    documents: [],
    applicable_field_groups: ['network_ids'],
    blocking_issues: [],
    completeness_by_tab: {},
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  authState.profile = { id: 'admin', role: 'admin', full_name: 'Admin' }
  vi.mocked(assetsApi.list).mockResolvedValue([assetRow()])
  vi.mocked(assetsApi.get).mockResolvedValue(detail())
  vi.mocked(assetMastersApi.listCategories).mockResolvedValue([PARENT_CATEGORY, LAPTOP_CATEGORY])
})

describe('AssetsPage — the register list', () => {
  it('counts gross block over capitalized assets only, not drafts', async () => {
    vi.mocked(assetsApi.list).mockResolvedValue([
      assetRow({ id: 'a1', lifecycle_status: 'capitalized', original_cost: '60000.00' }),
      assetRow({ id: 'a2', lifecycle_status: 'draft', original_cost: '99999.00' }),
    ])
    wrap(<AssetsPage />)

    expect(await screen.findByText('Gross block')).toBeInTheDocument()
    // A draft is not on the books; including it would overstate the balance sheet.
    expect(screen.getByText('Capitalized assets only')).toBeInTheDocument()
    expect(await screen.findByText(/1 draft not yet on the books/)).toBeInTheDocument()
  })

  it('lists assets with their tag and opens the detail page on click', async () => {
    const u = userEvent.setup()
    wrap(<AssetsPage />)

    expect(await screen.findByText('MacBook Pro')).toBeInTheDocument()
    expect(screen.getByText('COMP-000001')).toBeInTheDocument()

    await u.click(screen.getByText('MacBook Pro'))
    expect(navigate).toHaveBeenCalledWith('/app/assets/a1')
  })

  it('lets the user choose which columns the register shows', async () => {
    const u = userEvent.setup()
    wrap(<AssetsPage />)
    await screen.findByText('MacBook Pro')

    // 'Department' is not one of the default columns.
    expect(screen.queryByRole('columnheader', { name: 'Department' })).not.toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Columns' }))
    await u.click(await screen.findByRole('checkbox', { name: 'Department' }))
    await u.click(screen.getByRole('button', { name: 'Apply' }))

    expect(await screen.findByRole('columnheader', { name: 'Department' })).toBeInTheDocument()
  })

  it('offers the masters screen to admins only', async () => {
    wrap(<AssetsPage />)
    expect(await screen.findByRole('button', { name: 'Masters' })).toBeInTheDocument()
  })

  it('hides the masters screen from a non-admin', async () => {
    authState.profile = { id: 'e', role: 'employee', full_name: 'Emp' }
    wrap(<AssetsPage />)
    await screen.findByText('MacBook Pro')
    expect(screen.queryByRole('button', { name: 'Masters' })).not.toBeInTheDocument()
    // But they can still create — drafts are open to anyone with the module.
    expect(screen.getByRole('button', { name: 'Add asset' })).toBeInTheDocument()
  })
})

describe('QuickAddAssetModal — the six-field create form', () => {
  it('creates a draft and navigates to it, surfacing the category defaults', async () => {
    const u = userEvent.setup()
    vi.mocked(assetsApi.quickAdd).mockResolvedValue({
      acquisition_id: 'acq1',
      asset_ids: ['a1'],
      first_asset_id: 'a1',
      quantity: 1,
    })
    wrap(<AssetsPage />)
    await screen.findByText('MacBook Pro')

    // The split entry point: the quick-add modal now lives behind the menu.
    await u.click(screen.getByRole('button', { name: 'Add asset' }))
    await u.click(screen.getByRole('button', { name: 'New asset' }))
    await u.type(await screen.findByLabelText('Asset name'), 'Dell Latitude')

    // Choosing the parent auto-selects its single leaf and shows the statutory
    // defaults the user would otherwise never see being applied.
    await u.selectOptions(screen.getByLabelText('Category'), 'cat-parent')
    expect(await screen.findByText(/Useful life 3 yrs/)).toBeInTheDocument()
    expect(screen.getByText(/IT block PM-40-COMP/)).toBeInTheDocument()

    await u.click(screen.getByRole('button', { name: 'Create draft' }))

    await waitFor(() =>
      expect(assetsApi.quickAdd).toHaveBeenCalledWith(
        expect.objectContaining({
          asset_name: 'Dell Latitude',
          category_id: 'cat-leaf',
          quantity: 1,
        }),
      ),
    )
    expect(navigate).toHaveBeenCalledWith('/app/assets/a1')
  })

  it('requires a name and a category before calling the API', async () => {
    const u = userEvent.setup()
    wrap(<AssetsPage />)
    await screen.findByText('MacBook Pro')

    await u.click(screen.getByRole('button', { name: 'Add asset' }))
    await u.click(screen.getByRole('button', { name: 'New asset' }))
    await u.click(await screen.findByRole('button', { name: 'Create draft' }))

    expect(await screen.findByText('Required')).toBeInTheDocument()
    expect(screen.getByText('Pick a category and subcategory')).toBeInTheDocument()
    expect(assetsApi.quickAdd).not.toHaveBeenCalled()
  })

  it('warns that a quantity above one explodes into separate assets', async () => {
    const u = userEvent.setup()
    wrap(<AssetsPage />)
    await screen.findByText('MacBook Pro')

    await u.click(screen.getByRole('button', { name: 'Add asset' }))
    await u.click(screen.getByRole('button', { name: 'New asset' }))
    const qty = await screen.findByLabelText('Quantity')
    await u.clear(qty)
    await u.type(qty, '50')

    expect(await screen.findByText('Creates 50 separately tagged assets')).toBeInTheDocument()
  })
})

describe('AssetDetailPage — progressive disclosure', () => {
  it('shows the outstanding-items checklist and blocks submission until it is empty', async () => {
    vi.mocked(assetsApi.get).mockResolvedValue(
      detail({
        blocking_issues: [
          { field: 'invoice_number', label: 'Invoice number', tab: 'acquisition', kind: 'missing', message: null },
          { field: 'location_id', label: 'Location', tab: 'assignment', kind: 'missing', message: null },
          { field: 'doc:asset_photo', label: 'Asset photograph', tab: 'documents', kind: 'missing', message: null },
        ],
      }),
    )
    wrap(<AssetsPage />, '/app/assets/a1')

    expect(await screen.findByText('Needed before this can be submitted')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Invoice number' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Asset photograph' })).toBeInTheDocument()

    // The submit button counts what is missing rather than failing on click.
    expect(screen.getByRole('button', { name: '3 items outstanding' })).toBeDisabled()
  })

  it('deep-links a checklist item to the tab that owns the field', async () => {
    const u = userEvent.setup()
    vi.mocked(assetsApi.get).mockResolvedValue(
      detail({
        blocking_issues: [
          { field: 'location_id', label: 'Location', tab: 'assignment', kind: 'missing', message: null },
        ],
      }),
    )
    wrap(<AssetsPage />, '/app/assets/a1')

    await screen.findByText('Needed before this can be submitted')
    await u.click(screen.getByRole('button', { name: 'Location' }))

    expect(await screen.findByText('Assignment & location')).toBeInTheDocument()
  })

  it('allows submission once nothing is outstanding', async () => {
    const u = userEvent.setup()
    vi.mocked(assetsApi.submit).mockResolvedValue({ updated: ['a1'], lifecycle_status: 'ready' })
    wrap(<AssetsPage />, '/app/assets/a1')

    const submit = await screen.findByRole('button', { name: 'Submit for approval' })
    expect(submit).toBeEnabled()
    await u.click(submit)

    await waitFor(() =>
      expect(assetsApi.submit).toHaveBeenCalledWith('a1', { apply_to_siblings: false }),
    )
  })

  it('shows only the conditional field groups the category declares relevant', async () => {
    wrap(<AssetsPage />, '/app/assets/a1')
    await screen.findByRole('button', { name: 'Submit for approval' })

    // The laptop category declares network_ids, so IMEI appears...
    expect(await screen.findByLabelText('IMEI')).toBeInTheDocument()
    // ...and vehicle registration, which it does not declare, stays hidden.
    expect(screen.queryByLabelText('Chassis number')).not.toBeInTheDocument()
  })

  it('shows vehicle fields instead when the category declares registration', async () => {
    vi.mocked(assetsApi.get).mockResolvedValue(
      detail({ applicable_field_groups: ['registration'] }),
    )
    wrap(<AssetsPage />, '/app/assets/a1')
    await screen.findByRole('button', { name: 'Submit for approval' })

    expect(await screen.findByLabelText('Chassis number')).toBeInTheDocument()
    expect(screen.queryByLabelText('IMEI')).not.toBeInTheDocument()
  })

  it('locks the tag and depreciation inputs once the asset is capitalized', async () => {
    const u = userEvent.setup()
    vi.mocked(assetsApi.get).mockResolvedValue(
      detail({
        asset: assetRow({ lifecycle_status: 'capitalized', capitalization_date: '2026-04-10' }),
        siblings: [
          {
            id: 'a1',
            unit_index: 1,
            asset_code: 'COMP-000001',
            lifecycle_status: 'capitalized',
            manufacturer_serial_number: 'SN-1',
          },
        ],
      }),
    )
    wrap(<AssetsPage />, '/app/assets/a1')

    expect(await screen.findByText('On the books')).toBeInTheDocument()
    expect(await screen.findByLabelText('Asset code / tag')).toBeDisabled()

    await u.click(screen.getByRole('button', { name: /Depreciation/ }))
    expect(await screen.findByText(/locked because the asset is capitalized/)).toBeInTheDocument()
    expect(screen.getByLabelText('Useful life (months)')).toBeDisabled()
  })

  it('spells out the GST split that decides the depreciation base', async () => {
    const u = userEvent.setup()
    vi.mocked(assetsApi.get).mockResolvedValue(
      detail({
        acquisition: acquisition({
          itc_treatment: 'blocked',
          recoverable_gst: '0.00',
          capitalizable_gst: '10800.00',
          landed_cost: '70800.00',
        }),
      }),
    )
    wrap(<AssetsPage />, '/app/assets/a1')
    await screen.findByRole('button', { name: 'Submit for approval' })

    await u.click(screen.getByRole('button', { name: /Tax & GST/ }))

    expect(await screen.findByText('Capitalizable GST')).toBeInTheDocument()
    expect(screen.getByText('Added to asset cost and depreciated')).toBeInTheDocument()

    // Scoped per row: with ITC blocked, total GST and capitalizable GST are the
    // same figure, so a bare text match would not prove which row is which.
    const rowFor = (label: string) =>
      screen.getByText(label).closest('div')!.parentElement!
    expect(rowFor('Capitalizable GST')).toHaveTextContent('₹10,800.00')
    expect(rowFor('Recoverable GST')).toHaveTextContent('₹0.00')

    // The reason is stated, not left for the user to infer.
    expect(screen.getByText(/Credit is blocked/)).toBeInTheDocument()
  })

  it('offers a serial grid for an exploded batch instead of 50 separate visits', async () => {
    vi.mocked(assetsApi.get).mockResolvedValue(
      detail({
        acquisition: acquisition({ quantity: 3 }),
        siblings: [1, 2, 3].map((i) => ({
          id: `a${i}`,
          unit_index: i,
          asset_code: `COMP-00000${i}`,
          lifecycle_status: 'draft' as const,
          manufacturer_serial_number: null,
        })),
      }),
    )
    wrap(<AssetsPage />, '/app/assets/a1')

    expect(await screen.findByText('Batch of 3 units')).toBeInTheDocument()
    expect(screen.getByLabelText('Serial number for unit 2')).toBeInTheDocument()
    expect(screen.getByText('Unit 1 of 3')).toBeInTheDocument()
  })
})
