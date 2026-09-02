import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DepreciationTab } from './DepreciationTab'
import { ToastProvider } from '@/components/ui/Toast'
import type { AssetDetail } from '@/api/hooks/assets'

const run = {
  id: 'r1',
  company_id: 'c1',
  financial_year_id: 'fy-1',
  financial_year_label: '2024-25',
  run_date: '2025-03-31',
  status: 'finalized' as const,
  total_gross_block: 0,
  total_depreciation: 0,
  total_carrying_amount: 0,
  total_it_depreciation: 0,
  total_it_closing_wdv: 0,
  created_at: '2025-03-31T00:00:00Z',
  updated_at: '2025-03-31T00:00:00Z',
}

// Module scope so the assertion below can reach it through the mock closure.
const reopen = vi.fn().mockResolvedValue({ ...run, status: 'draft' })

vi.mock('@/api/hooks/depreciation', () => ({
  useDepreciationRuns: () => ({ data: [run], isLoading: false }),
  useCreateDepreciationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useFinalizeDepreciationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAssetDepreciationLines: () => ({ data: [], isLoading: false }),
  useReopenDepreciationRun: () => ({ mutateAsync: reopen, isPending: false }),
  useItBlockDepreciationLines: () => ({ data: [], isLoading: false }),
  useExplainDepreciation: () => ({ data: undefined, isLoading: false, error: null }),
}))
vi.mock('@/api/hooks/assets', () => ({
  useUpdateAsset: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('@/api/hooks/assetMasters', () => ({
  useItBlocks: () => ({ data: [] }),
  useAssetCategories: () => ({ data: [] }),
}))
const fyState = vi.hoisted(() => ({
  data: [
    {
      id: 'fy-1',
      company_id: 'c1',
      label: '2024-25',
      start_date: '2024-04-01',
      end_date: '2025-03-31',
      status: 'open' as 'open' | 'closed',
    },
  ],
}))

vi.mock('@/api/hooks/financialYears', () => ({
  useFinancialYears: () => ({ data: fyState.data, isLoading: false }),
}))
// Module scope so tests can flip roles without re-mocking.
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
    status: 'authenticated' as const,
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}))

// Only the fields this tab dereferences; reopen never touches acquisition data.
const detail = {
  asset: {
    id: 'a-1',
    category_id: 'cat-1',
    original_cost: '60000.00',
    warranty_expiry_date: null,
    useful_life_months: 36,
    dep_method: 'slm',
    residual_pct: '5.00',
    useful_life_override_reason: null,
    it_block_id: null,
    it_dep_rate: null,
    it_put_to_use_date: null,
    available_for_use_date: null,
    capitalization_date: null,
    warranty_start_date: null,
    warranty_months: null,
    is_pre_cutover: false,
    opening_accumulated_depreciation: null,
    opening_wdv: null,
    opening_it_wdv: null,
  },
  acquisition: {},
  siblings: [],
  documents: [],
  applicable_field_groups: [],
  blocking_issues: [],
  completeness_by_tab: {},
} as unknown as AssetDetail

describe('DepreciationTab — reopen finalized run', () => {
  it('asks for a reason and reopens', async () => {
    render(
      <ToastProvider>
        <DepreciationTab detail={detail} locked={false} />
      </ToastProvider>,
    )
    fireEvent.click(await screen.findByRole('button', { name: /reopen/i }))
    // Confirm stays locked until the backend's minimum reason length is met.
    expect(screen.getByRole('button', { name: /confirm reopen/i })).toBeDisabled()
    fireEvent.change(await screen.findByLabelText(/reason/i), {
      target: { value: 'Wrong opening WDV' },
    })
    fireEvent.click(screen.getByRole('button', { name: /confirm reopen/i }))
    await waitFor(() =>
      expect(reopen).toHaveBeenCalledWith(
        expect.objectContaining({ runId: 'r1', reason: 'Wrong opening WDV' }),
      ),
    )
  })

  it('is hidden from non-admins', async () => {
    authState.profile = { id: 'u2', role: 'employee', full_name: 'Emp' }
    render(
      <ToastProvider>
        <DepreciationTab detail={detail} locked={false} />
      </ToastProvider>,
    )
    await screen.findByText('Companies Act — Schedule II')
    expect(screen.queryByRole('button', { name: /reopen/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /finalize/i })).not.toBeInTheDocument()
  })

  it('disables reopen button when financial year is closed', async () => {
    authState.profile = { id: 'u1', role: 'admin', full_name: 'Admin' }
    fyState.data = [
      {
        id: 'fy-1',
        company_id: 'c1',
        label: '2024-25',
        start_date: '2024-04-01',
        end_date: '2025-03-31',
        status: 'closed' as const,
      },
    ]
    render(
      <ToastProvider>
        <DepreciationTab detail={detail} locked={false} />
      </ToastProvider>,
    )
    const btn = await screen.findByRole('button', { name: /reopen/i })
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('title', 'Financial year is closed. Reopen the financial year first.')
  })
})
