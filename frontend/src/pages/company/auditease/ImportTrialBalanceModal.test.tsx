import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '@/components/ui/Toast'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import { ImportTrialBalanceModal } from './ImportTrialBalanceModal'

vi.mock('@/api/endpoints/auditease', () => ({
  auditeaseCompanyApi: {
    inspectTrialBalance: vi.fn(),
    previewTrialBalance: vi.fn(),
    importTrialBalance: vi.fn(),
  },
}))

function renderModal() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <ImportTrialBalanceModal open onClose={vi.fn()} engagementId="eng-1" />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

const diagnostics = {
  header_row: 1, rows_scanned: 2, rows_imported: 1,
  rows_dropped_blank: 0, rows_dropped_total: 1, rows_dropped_repeated_header: 0,
  rows_section: 0, rows_error: 0,
  detected_convention: 'signed' as const, convention_confidence: 'proven',
  convention_evidence: ['negative balances sum to zero'], negative_closing_count: 1,
  explicit_marker_count: 0, derived_fields: [], total_debit: 0, total_credit: 0,
  debit_credit_difference: 0, movement_balanced: true, closing_sum: 0,
  closing_sums_to_zero: true, opening_sum: 0, opening_sums_to_zero: true,
  row_consistency_mismatches: 0, inconsistent_rows: [], sign_unresolved_count: 0,
  sheet_stated_total_debit: null, sheet_stated_total_credit: null,
  issues: [{ row: 3, kind: 'dropped' as const, reason: 'total / carried-forward row', raw: [] }],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(auditeaseCompanyApi.inspectTrialBalance).mockResolvedValue({
    sheets: [{
      name: 'Sheet1', headers: ['Ledger', 'Debit', 'Credit'],
      preview_rows: [['Sales', '', '-123123']], header_row: 1, first_data_row: 2,
      skipped_leading_rows: [],
      suggested_map: { ledger_name: 'Ledger', debit: 'Debit', credit: 'Credit' },
    }],
  })
  vi.mocked(auditeaseCompanyApi.previewTrialBalance).mockResolvedValue({
    diagnostics,
    sample_rows: [{
      row: 2, ledger_name: 'Sales', opening_balance: 0, debit: 0, credit: 123123,
      closing_balance: -123123, closing_net_debit: -123123, derived: [], notes: [],
    }],
    reimport_impact: null, would_import: 1, would_skip: 1,
  })
  vi.mocked(auditeaseCompanyApi.importTrialBalance).mockResolvedValue({
    imported: 1, skipped: 1, errors: [], total_debit: 0, total_credit: 0,
    balanced: true, accounts: [], diagnostics, sign_convention: 'signed', totals: null,
  })
})

describe('ImportTrialBalanceModal', () => {
  it('uses suggested mapping, previews without writing, and formats negative values consistently', async () => {
    const user = userEvent.setup()
    const rendered = renderModal()
    const input = rendered.container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'tb.csv', { type: 'text/csv' })] } })

    const previewButton = await screen.findByRole('button', { name: 'Check & preview' })
    expect(previewButton).toBeEnabled()
    await user.click(previewButton)

    await waitFor(() => expect(auditeaseCompanyApi.previewTrialBalance).toHaveBeenCalledTimes(1))
    expect(auditeaseCompanyApi.importTrialBalance).not.toHaveBeenCalled()
    expect(await screen.findByText('123,123.00 Cr')).toBeInTheDocument()
    expect(screen.queryByText('-123123')).not.toBeInTheDocument()
    expect(screen.getByText(/total row/)).toBeInTheDocument()

    const importButton = screen.getByRole('button', { name: 'Import anyway' })
    expect(importButton).toBeEnabled()
    await user.click(importButton)
    await waitFor(() => expect(auditeaseCompanyApi.importTrialBalance).toHaveBeenCalledTimes(1))
  })
})
