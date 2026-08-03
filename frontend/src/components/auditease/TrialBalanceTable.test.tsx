import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { TrialBalanceViewResponse } from '@/api/types'
import { TrialBalanceTable } from './TrialBalanceTable'

vi.mock('./GroupMappingCell', () => ({ GroupMappingCell: () => <span>Mapped</span> }))

const view = {
  accounts: [
    {
      id: 'income-1', company_id: 'company-1', engagement_id: 'eng-1',
      ledger_code: 'I1', ledger_name: 'Sales', mapped_group_id: 'group-1',
      mapped_group_path: ['Income', 'Revenue from Operations'], nature: 'credit',
      opening_balance: 0, debit: 0, credit: 0, closing_balance: -600,
      opening_net_debit: 0, closing_net_debit: -600,
      adjustment_net_debit: 0, final_net_debit: -600,
      presented_opening: 0, presented_closing: 600,
      presented_adjustment: 0, presented_final: 600,
      sign_unresolved: false, source_row_consistent: true,
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    },
  ],
  totals: {
    groups: [{
      key: 'Income', nature: 'credit', ledger_count: 1,
      opening_net_debit: 0, presented_opening: 0, debit: 0, credit: 0,
      closing_net_debit: -999, presented_closing: 999,
      adjustment_net_debit: 0, presented_adjustment: 0,
      final_net_debit: -999, presented_final: 999,
      net_debit: -999, presented: 999,
    }],
    assets: 0, liabilities: 0, income: 999, expenditure: 0, equity: 999,
    net_profit: 999, liabilities_plus_equity: 999, difference: 999,
    difference_including_unmapped: 999, balanced: false,
    unmapped_net_debit: 0, unmapped_count: 0, unresolved_nature_count: 0,
    sign_unresolved_count: 0, ledger_count: 1, mapped_count: 1,
    statement_ready: true, total_debit: 0, total_credit: 0, movement_balanced: true,
  },
  sign_convention: 'signed', sign_unresolved_count: 0,
  inconsistent_row_count: 0, warnings: [],
} satisfies TrialBalanceViewResponse

describe('TrialBalanceTable', () => {
  it('renders server subtotals and canonical Dr/Cr signs without recomputing', () => {
    render(<TrialBalanceTable view={view} readonly />)
    expect(screen.getAllByText('999.00 Cr').length).toBeGreaterThan(0)
    expect(screen.getAllByText('600.00 Cr').length).toBeGreaterThan(0)
  })
})
