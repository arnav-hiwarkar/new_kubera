import React, { useMemo, useState } from 'react'
import type {
  TBGroupSubtotalResponse,
  TrialBalanceAccountResponse,
  TrialBalanceViewResponse,
} from '@/api/types'
import { formatAmount, formatSigned, type AmountStyle } from '@/lib/format'
import { GroupMappingCell } from './GroupMappingCell'
import { EmptyState, Spinner } from '@/components/ui'

const ORDER = ['Assets', 'Liabilities', 'Income', 'Expenditure', 'Unmapped']
const EMPTY_ACCOUNTS: TrialBalanceAccountResponse[] = []

function initialStyle(): AmountStyle {
  try {
    const saved = localStorage.getItem('auditease.tb.signStyle')
    if (saved === 'drcr' || saved === 'signed' || saved === 'accounting') return saved
  } catch {
    // Storage can be unavailable in privacy mode and test environments.
  }
  return 'drcr'
}

function display(value: number, style: AmountStyle) {
  return <span className="whitespace-nowrap tabular-nums">{formatAmount(value, { style })}</span>
}

function movement(value: number) {
  return <span className="whitespace-nowrap tabular-nums">{formatSigned(value)}</span>
}

export function TrialBalanceTable({
  view,
  loading,
  readonly,
}: {
  view?: TrialBalanceViewResponse
  loading?: boolean
  readonly?: boolean
}) {
  const accounts = view?.accounts ?? EMPTY_ACCOUNTS
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [style, setStyle] = useState<AmountStyle>(initialStyle)

  const grouped = useMemo(() => {
    const result: Record<string, TrialBalanceAccountResponse[]> = { Unmapped: [] }
    for (const account of accounts) {
      const key = account.mapped_group_path?.[0] || 'Unmapped'
      ;(result[key] ??= []).push(account)
    }
    return result
  }, [accounts])

  const subtotals = useMemo(
    () => new Map((view?.totals.groups ?? []).map((group) => [group.key, group])),
    [view],
  )

  const setAmountStyle = (next: AmountStyle) => {
    setStyle(next)
    try {
      localStorage.setItem('auditease.tb.signStyle', next)
    } catch {
      // Display preference remains session-local when storage is unavailable.
    }
  }

  if (loading) return <Spinner className="mx-auto mt-8 h-6 w-6" />
  if (accounts.length === 0) {
    return (
      <EmptyState
        title="No trial balance imported"
        description={readonly ? 'The company has not imported a trial balance yet.' : 'Import a trial balance to see ledgers here.'}
      />
    )
  }

  const names = Object.keys(grouped)
    .filter((name) => grouped[name].length > 0)
    .sort((a, b) => {
      const ai = ORDER.indexOf(a)
      const bi = ORDER.indexOf(b)
      return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || a.localeCompare(b)
    })

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-bg-surface shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2">
        <div className="text-xs text-text-muted">
          Final figures include approved audit adjustments.
        </div>
        <div className="flex rounded-md border border-border p-0.5 text-xs" aria-label="Amount style">
          {(['drcr', 'signed', 'accounting'] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setAmountStyle(option)}
              className={`rounded px-2 py-1 ${style === option ? 'bg-accent text-accent-contrast' : 'text-text-secondary'}`}
            >
              {option === 'drcr' ? 'Dr/Cr' : option === 'signed' ? 'Signed' : 'Accounting'}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-text-secondary">
          <thead className="bg-bg-inset text-xs font-medium uppercase tracking-wider text-text-muted">
            <tr>
              <th className="px-4 py-3">Code / Ledger</th>
              <th className="px-4 py-3">Group Mapping</th>
              <th className="px-4 py-3 text-right">Opening</th>
              <th className="px-4 py-3 text-right">Debit</th>
              <th className="px-4 py-3 text-right">Credit</th>
              <th className="px-4 py-3 text-right">Closing</th>
              <th className="px-4 py-3 text-right">Adjustment</th>
              <th className="px-4 py-3 text-right">Final</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {names.map((name) => (
              <GroupRows
                key={name}
                name={name}
                accounts={grouped[name]}
                subtotal={subtotals.get(name)}
                expanded={expanded[name] ?? true}
                toggle={() => setExpanded((current) => ({ ...current, [name]: !(current[name] ?? true) }))}
                style={style}
                readonly={readonly}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function GroupRows({
  name,
  accounts,
  subtotal,
  expanded,
  toggle,
  style,
  readonly,
}: {
  name: string
  accounts: TrialBalanceAccountResponse[]
  subtotal?: TBGroupSubtotalResponse
  expanded: boolean
  toggle: () => void
  style: AmountStyle
  readonly?: boolean
}) {
  return (
    <React.Fragment>
      <tr className="cursor-pointer bg-bg-inset/50 hover:bg-bg-inset" onClick={toggle}>
        <td className="px-4 py-3 font-semibold text-text-primary" colSpan={2}>
          <div className="flex items-center gap-2">
            <span aria-hidden>{expanded ? '⌄' : '›'}</span>
            {name}
            <span className="text-xs font-normal text-text-muted">({accounts.length})</span>
            {subtotal?.nature && (
              <span className="rounded bg-bg-raised px-1.5 py-0.5 text-[10px] uppercase text-text-muted">
                {subtotal.nature}
              </span>
            )}
            {name === 'Unmapped' && (
              <span className="text-xs font-normal text-status-pending">excluded from statements</span>
            )}
          </div>
        </td>
        <td className="px-4 py-3 text-right font-medium">{display(subtotal?.opening_net_debit ?? 0, style)}</td>
        <td className="px-4 py-3 text-right font-medium">{movement(subtotal?.debit ?? 0)}</td>
        <td className="px-4 py-3 text-right font-medium">{movement(subtotal?.credit ?? 0)}</td>
        <td className="px-4 py-3 text-right font-medium">{display(subtotal?.closing_net_debit ?? 0, style)}</td>
        <td className="px-4 py-3 text-right font-medium">{display(subtotal?.adjustment_net_debit ?? 0, style)}</td>
        <td className="px-4 py-3 text-right font-semibold text-text-primary">{display(subtotal?.final_net_debit ?? subtotal?.net_debit ?? 0, style)}</td>
      </tr>
      {expanded && accounts.map((account) => (
        <tr key={account.id} className="hover:bg-bg-inset/30">
          <td className="px-4 py-3 pl-10">
            <div className="flex flex-col gap-1">
              <span className="font-medium text-text-primary">{account.ledger_name}</span>
              {account.ledger_code && <span className="text-xs text-text-muted">{account.ledger_code}</span>}
              <div className="flex gap-1">
                {account.sign_unresolved && <span className="text-xs text-status-pending">Sign unresolved</span>}
                {account.source_row_consistent === false && <span className="text-xs text-status-action">Source mismatch</span>}
              </div>
            </div>
          </td>
          <td className="px-4 py-3" onClick={(event) => event.stopPropagation()}>
            <GroupMappingCell accountId={account.id} currentGroupId={account.mapped_group_id ?? null} readonly={readonly} />
          </td>
          <td className="px-4 py-3 text-right">{display(account.opening_net_debit, style)}</td>
          <td className="px-4 py-3 text-right">{movement(account.debit)}</td>
          <td className="px-4 py-3 text-right">{movement(account.credit)}</td>
          <td className="px-4 py-3 text-right">{display(account.closing_net_debit, style)}</td>
          <td className="px-4 py-3 text-right">{display(account.adjustment_net_debit, style)}</td>
          <td className="px-4 py-3 text-right font-medium text-text-primary">{display(account.final_net_debit, style)}</td>
        </tr>
      ))}
    </React.Fragment>
  )
}
