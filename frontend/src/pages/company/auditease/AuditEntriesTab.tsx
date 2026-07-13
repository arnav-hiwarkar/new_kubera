import { useState } from 'react'
import { Card, Button, Spinner, StatusBadge, EmptyState, useToast } from '@/components/ui'
import { useListEntries, useApproveRejectEntry } from '@/api/hooks/auditease'
import { formatMoney } from '@/lib/format'

export function AuditEntriesTab({ engagementId }: { engagementId: string }) {
  const { data: entries = [], isLoading } = useListEntries(engagementId)
  const approveReject = useApproveRejectEntry()
  const toast = useToast()

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />
  if (entries.length === 0) {
    return (
      <EmptyState
        title="No audit entries yet"
        description="The auditor has not proposed any adjusting journal entries."
      />
    )
  }

  const handleAction = async (entryId: string, action: 'approved' | 'rejected') => {
    try {
      await approveReject.mutateAsync({ entryId, body: { status: action } })
      toast.success(`Entry ${action}`)
    } catch (e: any) {
      toast.error(e.message || `Failed to ${action} entry`)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Audit Entries</h3>
          <p className="text-sm text-text-muted">Review and approve adjusting journal entries proposed by the auditor.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6">
        {entries.map((entry) => {
          const totalDebit = entry.lines.filter((l) => l.side === 'debit').reduce((s, l) => s + l.amount, 0)
          const totalCredit = entry.lines.filter((l) => l.side === 'credit').reduce((s, l) => s + l.amount, 0)

          return (
            <Card key={entry.id} className="flex flex-col gap-4">
              <div className="flex items-start justify-between border-b border-border pb-3">
                <div>
                  <h4 className="text-base font-semibold text-text-primary">
                    {entry.code ? `${entry.code} - ` : ''}{entry.description}
                  </h4>
                  <div className="mt-1 flex items-center gap-2">
                    <StatusBadge status={entry.status} />
                    <span className="text-xs text-text-muted">
                      Created on {new Date(entry.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                {entry.status === 'proposed' && (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleAction(entry.id, 'rejected')}
                      loading={approveReject.isPending}
                    >
                      Reject
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleAction(entry.id, 'approved')}
                      loading={approveReject.isPending}
                    >
                      Approve
                    </Button>
                  </div>
                )}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-text-secondary">
                  <thead className="border-b border-border bg-background-subtle text-xs uppercase text-text-muted">
                    <tr>
                      <th className="px-4 py-2 font-medium">Ledger</th>
                      <th className="px-4 py-2 text-right font-medium">Debit</th>
                      <th className="px-4 py-2 text-right font-medium">Credit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {entry.lines.map((line) => (
                      <tr key={line.id} className="hover:bg-background-subtle/50">
                        <td className="px-4 py-2">{line.ledger_name}</td>
                        <td className="px-4 py-2 text-right">
                          {line.side === 'debit' ? formatMoney(line.amount) : '—'}
                        </td>
                        <td className="px-4 py-2 text-right">
                          {line.side === 'credit' ? formatMoney(line.amount) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="border-t border-border font-medium text-text-primary">
                    <tr>
                      <td className="px-4 py-2 text-right">Total</td>
                      <td className="px-4 py-2 text-right">{formatMoney(totalDebit)}</td>
                      <td className="px-4 py-2 text-right">{formatMoney(totalCredit)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
