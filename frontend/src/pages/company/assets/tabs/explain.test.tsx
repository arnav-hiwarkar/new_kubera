import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ToastProvider } from '@/components/ui/Toast'
import type { CalcTrace } from '@/components/calc'

const fy = {
  id: 'fy-1',
  company_id: 'c1',
  label: '2024-25',
  start_date: '2024-04-01',
  end_date: '2025-03-31',
  status: 'open' as const,
}

const run = {
  id: 'r1',
  company_id: 'c1',
  financial_year_id: 'fy-1',
  financial_year_label: '2024-25',
  run_date: '2025-03-31',
  status: 'draft' as const,
  total_gross_block: 0,
  total_depreciation: 0,
  total_carrying_amount: 0,
  total_it_depreciation: 0,
  total_it_closing_wdv: 0,
  created_at: '2025-03-31T00:00:00Z',
  updated_at: '2025-03-31T00:00:00Z',
}

const recordedTrace: CalcTrace = {
  title: 'Depreciation — Companies Act Schedule II — FY 2024-25',
  basis: 'SLM — straight line; useful life 60 months; residual 5.00%; original cost 100,000.00',
  is_projection: false,
  computed_at: '2025-04-01T10:00:00Z',
  steps: [
    { key: 'depreciable_base', group: 'Rate', label: 'Depreciable base', formula: 'Original cost − Residual value', substitution: '100,000.00 − 5,000.00', result: '95,000.00', unit: 'money', emphasis: false },
    { key: 'depreciation_for_year', group: 'Charge for the year', label: 'Depreciation for the year', formula: 'x', substitution: 'y', result: '19,000.00', unit: 'money', emphasis: true },
  ],
}

const projectedTrace: CalcTrace = { ...recordedTrace, is_projection: true, computed_at: null }

const line = (calc_trace: CalcTrace | null) => ({
  id: 'l1',
  run_id: 'r1',
  asset_id: 'asset-1',
  method: 'SLM',
  opening_gross_block: '100000.00',
  additions: '0.00',
  disposals: '0.00',
  closing_gross_block: '100000.00',
  opening_accumulated_depreciation: '0.00',
  depreciation_for_year: '19000.00',
  disposal_accumulated_depreciation: '0.00',
  closing_accumulated_depreciation: '19000.00',
  opening_carrying_amount: '100000.00',
  closing_carrying_amount: '81000.00',
  residual_value: '5000.00',
  remaining_useful_life_days: 1460,
  effective_rate_pct: '19.00',
  is_part_year: false,
  is_disposed: false,
  gain_loss_on_disposal: null,
  calc_trace,
})

const explain = vi.fn()
let lines: unknown[] = []

vi.mock('@/api/hooks/depreciation', () => ({
  useDepreciationRuns: () => ({ data: [run], isLoading: false }),
  useCreateDepreciationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useFinalizeDepreciationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReopenDepreciationRun: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAssetDepreciationLines: () => ({ data: lines, isLoading: false }),
  useItBlockDepreciationLines: () => ({ data: [], isLoading: false }),
  useExplainDepreciation: (_a: string, _f: string, enabled: boolean) =>
    enabled
      ? { data: explain(), isLoading: false, error: null }
      : { data: undefined, isLoading: false, error: null },
}))
vi.mock('@/api/hooks/financialYears', () => ({
  useFinancialYears: () => ({ data: [fy], isLoading: false }),
}))
vi.mock('@/auth/company', () => ({ useCompanyAuth: () => ({ profile: { role: 'admin' } }) }))

const { DepreciationRunCard } = await import('./DepreciationRunCard')

function renderCard() {
  return render(
    <ToastProvider>
      <DepreciationRunCard assetId="asset-1" itBlockId={null} />
    </ToastProvider>,
  )
}

describe('DepreciationRunCard calculation drawer', () => {
  it('opens the recorded trace from the header link', async () => {
    lines = [line(recordedTrace)]
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /see the calculation/i }))

    await waitFor(() => expect(screen.getByText('Depreciable base')).toBeTruthy())
    expect(screen.getByText(/Computed/)).toBeTruthy()
    expect(screen.queryByText(/not the recorded figure/i)).toBeNull()
  })

  it('deep-links from a stat tile to that figure', async () => {
    lines = [line(recordedTrace)]
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /how was depreciation \(fy\) calculated/i }))

    await waitFor(() =>
      expect(document.getElementById('calc-step-depreciation_for_year')?.getAttribute('data-focused')).toBe('true'),
    )
  })

  it('projects when no run exists for the year', async () => {
    lines = []
    explain.mockReturnValue({ companies_act: projectedTrace, income_tax: null })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /see the calculation/i }))

    await waitFor(() => expect(screen.getByText(/not the recorded figure/i)).toBeTruthy())
  })

  it('says so when a run predates traces, and offers a projection', async () => {
    lines = [line(null)]
    explain.mockReturnValue({ companies_act: projectedTrace, income_tax: null })
    renderCard()

    fireEvent.click(screen.getByRole('button', { name: /see the calculation/i }))
    await waitFor(() =>
      expect(screen.getByText(/before calculation traces were kept/i)).toBeTruthy(),
    )
    // It does not silently substitute a projection for the recorded figure.
    expect(screen.queryByText('Depreciable base')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /projection/i }))
    await waitFor(() => expect(screen.getByText(/not the recorded figure/i)).toBeTruthy())
  })

  it('does not fetch a projection until the drawer is opened', () => {
    lines = []
    explain.mockClear()
    explain.mockReturnValue({ companies_act: projectedTrace, income_tax: null })
    renderCard()

    expect(explain).not.toHaveBeenCalled()
  })
})
