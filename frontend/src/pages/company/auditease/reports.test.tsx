import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { ReportsTab } from './ReportsTab'
import type { ReportPreviewResponse } from '@/api/types'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'

vi.mock('@/api/endpoints/auditease', () => ({
  auditeaseCompanyApi: {
    previewReport: vi.fn(),
    generateReport: vi.fn().mockResolvedValue({ id: 'doc-1', url: '/download' }),
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

const preview: ReportPreviewResponse = {
  period_label: 'FY24',
  lines: [
    {
      ledger_id: 'l1',
      ledger_name: 'Cash',
      ledger_code: 'A1',
      top_group: 'Assets',
      group_path: ['Assets', 'Cash and Cash Equivalents'],
      closing: 1000,
      adjustment: 200,
      final: 1200,
    },
    {
      ledger_id: 'l2',
      ledger_name: 'Loan',
      ledger_code: 'L1',
      top_group: 'Liabilities',
      group_path: ['Liabilities', 'Trade Payables'],
      closing: 600,
      adjustment: 0,
      final: 600,
    },
    {
      ledger_id: 'l3',
      ledger_name: 'Sales',
      ledger_code: 'I1',
      top_group: 'Income',
      group_path: ['Income', 'Revenue from Operations'],
      closing: 500,
      adjustment: 0,
      final: 700,
    },
    {
      ledger_id: 'l4',
      ledger_name: 'Rent',
      ledger_code: 'E1',
      top_group: 'Expenditure',
      group_path: ['Expenditure', 'Other Expenses'],
      closing: 100,
      adjustment: 0,
      final: 100,
    },
  ],
  totals: { assets: 1200, liabilities: 600, income: 700, expenditure: 100 },
  net_profit: 600,
  balance_check: { assets: 1200, liabilities_plus_equity: 1200, difference: 0, balanced: true },
  entries: {
    approved: [{ id: 'e1', code: 'AJE-1', description: 'Extra sale', total: 200, line_count: 2 }],
    approved_count: 1,
    proposed_count: 1,
  },
  unmapped_count: 1,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ReportsTab preview', () => {
  it('renders the balance status, statements, net profit and warnings', async () => {
    (auditeaseCompanyApi.previewReport as ReturnType<typeof vi.fn>).mockResolvedValue(preview)
    wrap(<ReportsTab engagementId="eng-1" />)

    // Balance badge
    expect(await screen.findByText(/Balanced/)).toBeInTheDocument()
    // Unmapped warning
    expect(screen.getByText(/1 unmapped ledger/)).toBeInTheDocument()
    // Statement sections
    expect(screen.getByText('Balance Sheet')).toBeInTheDocument()
    expect(screen.getByText('Profit & Loss')).toBeInTheDocument()
    // Net profit figure
    expect(screen.getByText('Net Profit')).toBeInTheDocument()
    // Approved adjusting entry shows up
    expect(screen.getByText('Extra sale')).toBeInTheDocument()
    // Proposed-not-reflected note
    expect(screen.getByText(/awaiting approval/)).toBeInTheDocument()
  })

  it('calls generateReport when the Generate button is clicked', async () => {
    (auditeaseCompanyApi.previewReport as ReturnType<typeof vi.fn>).mockResolvedValue(preview)
    const user = userEvent.setup()
    wrap(<ReportsTab engagementId="eng-1" />)

    const btn = await screen.findByRole('button', { name: /Generate & Save/ })
    await user.click(btn)
    await waitFor(() => expect(auditeaseCompanyApi.generateReport).toHaveBeenCalledWith('eng-1'))
  })

  it('shows an empty state when there is nothing mapped', async () => {
    (auditeaseCompanyApi.previewReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...preview,
      lines: [],
    })
    wrap(<ReportsTab engagementId="eng-1" />)
    expect(await screen.findByText('Nothing to report yet')).toBeInTheDocument()
  })
})
