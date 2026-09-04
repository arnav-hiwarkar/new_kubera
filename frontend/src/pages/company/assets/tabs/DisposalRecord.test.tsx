/**
 * The disposal record used to be write-only: you could dispose an asset and
 * then never see the date, proceeds, buyer or invoice you had typed. These pin
 * that it reads back, and that it reads back for a non-admin too — performing a
 * disposal is admin-only, reading the register is not.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HistoryTab } from './HistoryTab'
import type { AssetDetail } from '@/api/hooks/assets'

vi.mock('@/api/hooks/activity', () => ({
  useActivityLog: () => ({
    data: [
      {
        id: 'log-1',
        action: 'asset.disposed',
        actor_id: 'u-admin',
        created_at: '2024-09-30T10:00:00Z',
      },
    ],
    isLoading: false,
  }),
}))
vi.mock('@/api/endpoints/users', () => ({
  usersApi: {
    list: vi.fn().mockResolvedValue([
      { id: 'u-admin', full_name: 'Priya Admin' },
      { id: 'u-emp', full_name: 'Ravi Employee' },
    ]),
  },
}))

function detail(assetOverrides: Record<string, unknown>): AssetDetail {
  return {
    asset: {
      id: 'a1',
      asset_name: 'Rack Server',
      asset_code: 'SRV-000001',
      lifecycle_status: 'capitalized',
      capitalization_date: '2024-04-01',
      original_cost: '500000.00',
      created_by: 'u-emp',
      submitted_by: 'u-emp',
      submitted_at: '2024-04-01T00:00:00Z',
      approved_by: 'u-admin',
      approved_at: '2024-04-02T00:00:00Z',
      ...assetOverrides,
    },
    acquisition: null,
    siblings: [],
    documents: [],
    blocking_issues: [],
  } as unknown as AssetDetail
}

const DISPOSED = {
  lifecycle_status: 'disposed',
  disposal_date: '2024-09-30',
  disposal_type: 'sale',
  sale_proceeds: '12345.67',
  disposal_it_proceeds: '12345.67',
  buyer_name: 'Acme Scrap Co',
  disposal_invoice_no: 'INV-DISP-9',
  disposal_remarks: 'End of life',
  disposed_by: 'u-admin',
}

function wrap(d: AssetDetail) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <HistoryTab detail={d} />
    </QueryClientProvider>,
  )
}

describe('HistoryTab — disposal record', () => {
  it('reads the whole disposal record back on a disposed asset', async () => {
    wrap(detail(DISPOSED))

    expect(await screen.findByText('Disposal')).toBeInTheDocument()
    expect(screen.getByText('30 Sep 2024')).toBeInTheDocument()
    expect(screen.getByText('Sale')).toBeInTheDocument()
    expect(screen.getByText('₹12,345.67')).toBeInTheDocument()
    expect(screen.getByText('Acme Scrap Co')).toBeInTheDocument()
    expect(screen.getByText('INV-DISP-9')).toBeInTheDocument()
    expect(screen.getByText('End of life')).toBeInTheDocument()
    // Non-repudiation replaces a segregation-of-duties rule here, so the actor
    // has to be named, not left as a raw id.
    expect(await screen.findByText('Priya Admin')).toBeInTheDocument()
  })

  it('shows no disposal section while the asset is still on the books', () => {
    wrap(detail({}))
    expect(screen.queryByText('Disposal')).not.toBeInTheDocument()
  })

  it('hides the tax consideration when it matches the book proceeds', () => {
    wrap(detail(DISPOSED))
    expect(
      screen.queryByText('Sale consideration for Income Tax'),
    ).not.toBeInTheDocument()
  })

  it('surfaces the tax consideration when it diverges from the book figure', () => {
    wrap(detail({ ...DISPOSED, disposal_it_proceeds: '9000.00' }))
    expect(screen.getByText('Sale consideration for Income Tax')).toBeInTheDocument()
    expect(screen.getByText('₹9,000.00')).toBeInTheDocument()
  })

  it('treats a differently-scaled decimal as the same figure, not a divergence', () => {
    // Both columns are serialised Decimals; "12345.670" must not read as a
    // divergence from "12345.67".
    wrap(detail({ ...DISPOSED, disposal_it_proceeds: '12345.670' }))
    expect(
      screen.queryByText('Sale consideration for Income Tax'),
    ).not.toBeInTheDocument()
  })

  it('labels the disposal entry in the audit trail', async () => {
    wrap(detail(DISPOSED))
    expect(await screen.findByText('Disposed')).toBeInTheDocument()
    expect(screen.queryByText('asset.disposed')).not.toBeInTheDocument()
  })
})
