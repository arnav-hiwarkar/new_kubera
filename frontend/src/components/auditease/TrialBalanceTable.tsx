import React, { useState, useMemo } from 'react'
import type { TrialBalanceAccountResponse } from '@/api/types'
import { formatMoney } from '@/lib/format'
import { GroupMappingCell } from './GroupMappingCell'
import { Spinner, EmptyState } from '@/components/ui'
import { cn } from '@/lib/cn'

const ChevronDownIcon = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
  </svg>
)

const ChevronRightIcon = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={className}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
  </svg>
)

const money = (v: number) => <span className="tabular-nums">{formatMoney(v)}</span>

export function TrialBalanceTable({
  accounts,
  loading,
}: {
  accounts: TrialBalanceAccountResponse[]
  loading?: boolean
}) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({})

  // Group accounts by their top-level group
  // mapped_group_path is [Top, Sub, ...] or null
  const grouped = useMemo(() => {
    const groups: Record<string, TrialBalanceAccountResponse[]> = {
      Unmapped: [],
    }
    for (const acc of accounts) {
      if (!acc.mapped_group_path || acc.mapped_group_path.length === 0) {
        groups.Unmapped.push(acc)
      } else {
        const top = acc.mapped_group_path[0]
        if (!groups[top]) groups[top] = []
        groups[top].push(acc)
      }
    }
    return groups
  }, [accounts])

  if (loading) {
    return <Spinner className="mx-auto mt-8 h-6 w-6" />
  }

  if (accounts.length === 0) {
    return (
      <EmptyState
        title="No trial balance imported"
        description="Import a trial balance to see ledgers here."
      />
    )
  }

  const toggleGroup = (grp: string) => {
    setExpandedGroups((prev) => ({ ...prev, [grp]: !prev[grp] }))
  }

  // Define the order of groups
  const order = ['Assets', 'Liabilities', 'Income', 'Expenditure', 'Unmapped']
  const sortedGroupNames = Object.keys(grouped).sort((a, b) => {
    const idxA = order.indexOf(a)
    const idxB = order.indexOf(b)
    if (idxA !== -1 && idxB !== -1) return idxA - idxB
    if (idxA !== -1) return -1
    if (idxB !== -1) return 1
    return a.localeCompare(b)
  })

  return (
    <div className="w-full overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-text-secondary">
          <thead className="bg-background-subtle text-xs font-medium uppercase tracking-wider text-text-muted">
            <tr>
              <th className="px-4 py-3">Code / Ledger</th>
              <th className="px-4 py-3">Group Mapping</th>
              <th className="px-4 py-3 text-right">Opening</th>
              <th className="px-4 py-3 text-right">Debit</th>
              <th className="px-4 py-3 text-right">Credit</th>
              <th className="px-4 py-3 text-right">Closing</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sortedGroupNames.map((groupName) => {
              const groupAccounts = grouped[groupName]
              if (groupAccounts.length === 0) return null
              
              const isExpanded = expandedGroups[groupName] ?? true
              
              const totalOp = groupAccounts.reduce((s, a) => s + a.opening_balance, 0)
              const totalDr = groupAccounts.reduce((s, a) => s + a.debit, 0)
              const totalCr = groupAccounts.reduce((s, a) => s + a.credit, 0)
              const totalCl = groupAccounts.reduce((s, a) => s + a.closing_balance, 0)

              return (
                <React.Fragment key={groupName}>
                  <tr
                    className="cursor-pointer bg-background-subtle/50 hover:bg-background-subtle"
                    onClick={() => toggleGroup(groupName)}
                  >
                    <td className="px-4 py-3 font-semibold text-text-primary" colSpan={2}>
                      <div className="flex items-center gap-2">
                        {isExpanded ? (
                          <ChevronDownIcon className="h-4 w-4" />
                        ) : (
                          <ChevronRightIcon className="h-4 w-4" />
                        )}
                        {groupName} <span className="text-xs font-normal text-text-muted">({groupAccounts.length})</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-medium">{money(totalOp)}</td>
                    <td className="px-4 py-3 text-right font-medium">{money(totalDr)}</td>
                    <td className="px-4 py-3 text-right font-medium">{money(totalCr)}</td>
                    <td className="px-4 py-3 text-right font-medium">{money(totalCl)}</td>
                  </tr>
                  
                  {isExpanded &&
                    groupAccounts.map((a) => (
                      <tr key={a.id} className="hover:bg-background-subtle/30">
                        <td className="px-4 py-3 pl-10">
                          <div className="flex flex-col">
                            <span className="font-medium text-text-primary">{a.ledger_name}</span>
                            {a.ledger_code && <span className="text-xs text-text-muted">{a.ledger_code}</span>}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <GroupMappingCell accountId={a.id} currentGroupId={a.mapped_group_id} />
                        </td>
                        <td className="px-4 py-3 text-right">{money(a.opening_balance)}</td>
                        <td className="px-4 py-3 text-right">{money(a.debit)}</td>
                        <td className="px-4 py-3 text-right">{money(a.credit)}</td>
                        <td className="px-4 py-3 text-right">{money(a.closing_balance)}</td>
                      </tr>
                    ))}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

