import { DataTable, type Column } from '@/components/ui'
import type { TrialBalanceAccountResponse } from '@/api/types'
import { formatMoney } from '@/lib/format'

const money = (v: number) => <span className="tabular-nums">{formatMoney(v)}</span>

const columns: Column<TrialBalanceAccountResponse>[] = [
  {
    key: 'ledger_code',
    header: 'Code',
    sortValue: (a) => a.ledger_code ?? '',
    cell: (a) => <span className="text-text-muted">{a.ledger_code ?? '—'}</span>,
  },
  {
    key: 'ledger_name',
    header: 'Ledger',
    sortValue: (a) => a.ledger_name.toLowerCase(),
    cell: (a) => <span className="font-medium text-text-primary">{a.ledger_name}</span>,
  },
  { key: 'opening_balance', header: 'Opening', align: 'right', sortValue: (a) => a.opening_balance, cell: (a) => money(a.opening_balance) },
  { key: 'debit', header: 'Debit', align: 'right', sortValue: (a) => a.debit, cell: (a) => money(a.debit) },
  { key: 'credit', header: 'Credit', align: 'right', sortValue: (a) => a.credit, cell: (a) => money(a.credit) },
  { key: 'closing_balance', header: 'Closing', align: 'right', sortValue: (a) => a.closing_balance, cell: (a) => money(a.closing_balance) },
]

export function TrialBalanceTable({
  accounts,
  loading,
}: {
  accounts: TrialBalanceAccountResponse[]
  loading?: boolean
}) {
  return (
    <DataTable
      columns={columns}
      data={accounts}
      rowKey={(a) => a.id}
      loading={loading}
      searchAccessors={(a) => `${a.ledger_code ?? ''} ${a.ledger_name}`}
      searchPlaceholder="Search ledgers…"
      pageSize={15}
      emptyTitle="No trial balance imported"
      emptyDescription="Import a trial balance to see ledgers here."
    />
  )
}
