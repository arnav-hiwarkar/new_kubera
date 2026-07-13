import { Card, Button, Spinner, useToast, EmptyState } from '@/components/ui'
import { usePreviewReport, useGenerateReport } from '@/api/hooks/auditease'
import { formatMoney } from '@/lib/format'
import { cn } from '@/lib/cn'
import type { ReportLine, ReportPreviewResponse } from '@/api/types'

const num = (v: number) => <span className="tabular-nums">{formatMoney(v)}</span>

/** One statement block (e.g. Balance Sheet or P&L), listing the ledgers that fall
 * under the given top-level groups with per-section subtotals. */
function StatementSection({
  title,
  groups,
  lines,
}: {
  title: string
  groups: string[]
  lines: ReportLine[]
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-bg-surface">
      <table className="w-full text-left text-sm text-text-secondary">
        <thead className="bg-background-subtle text-xs font-medium uppercase tracking-wider text-text-muted">
          <tr>
            <th className="px-4 py-2">Ledger</th>
            <th className="px-4 py-2 text-right">Closing</th>
            <th className="px-4 py-2 text-right">Adjustment</th>
            <th className="px-4 py-2 text-right">Final</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {groups.map((group) => {
            const rows = lines.filter((l) => l.top_group === group)
            if (rows.length === 0) return null
            const subtotal = rows.reduce((s, r) => s + r.final, 0)
            return (
              <ReportGroupBlock key={group} group={group} rows={rows} subtotal={subtotal} />
            )
          })}
        </tbody>
      </table>
      <div className="border-t border-border px-4 py-2 text-right text-sm font-semibold text-text-primary">
        {title} total{' '}
        {num(lines.filter((l) => groups.includes(l.top_group ?? '')).reduce((s, r) => s + r.final, 0))}
      </div>
    </div>
  )
}

function ReportGroupBlock({
  group,
  rows,
  subtotal,
}: {
  group: string
  rows: ReportLine[]
  subtotal: number
}) {
  return (
    <>
      <tr className="bg-background-subtle/50">
        <td className="px-4 py-2 font-semibold text-text-primary" colSpan={3}>
          {group}
        </td>
        <td className="px-4 py-2 text-right font-semibold text-text-primary">{num(subtotal)}</td>
      </tr>
      {rows.map((r) => {
        const subPath = (r.group_path ?? []).slice(1).join(' › ')
        return (
          <tr key={r.ledger_id} className="hover:bg-background-subtle/30">
            <td className="px-4 py-2 pl-8">
              <div className="font-medium text-text-primary">{r.ledger_name}</div>
              {subPath && <div className="text-xs text-text-muted">{subPath}</div>}
            </td>
            <td className="px-4 py-2 text-right">{num(r.closing)}</td>
            <td
              className={cn(
                'px-4 py-2 text-right',
                r.adjustment !== 0 && 'font-medium text-status-submitted',
              )}
            >
              {r.adjustment !== 0 ? num(r.adjustment) : '—'}
            </td>
            <td className="px-4 py-2 text-right font-medium text-text-primary">{num(r.final)}</td>
          </tr>
        )
      })}
    </>
  )
}

function ReportBody({ report }: { report: ReportPreviewResponse }) {
  const { totals, balance_check: bc, net_profit } = report
  const profitLabel = net_profit >= 0 ? 'Net Profit' : 'Net Loss'

  return (
    <div className="flex flex-col gap-6">
      {/* Balance status + unmapped warning */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={cn(
            'inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium',
            bc.balanced
              ? 'text-status-verified badge-bg-verified'
              : 'text-status-action badge-bg-action',
          )}
        >
          {bc.balanced ? '● Balanced' : `● Not balanced — difference ${formatMoney(bc.difference)}`}
        </span>
        {report.unmapped_count > 0 && (
          <span className="rounded-md bg-status-pending/10 px-3 py-1 text-sm text-status-pending">
            {report.unmapped_count} unmapped ledger{report.unmapped_count > 1 ? 's' : ''} excluded from
            these statements
          </span>
        )}
      </div>

      {/* Balance Sheet */}
      <div>
        <h4 className="mb-2 text-base font-semibold text-text-primary">Balance Sheet</h4>
        <StatementSection title="Assets" groups={['Assets']} lines={report.lines} />
        <div className="h-3" />
        <StatementSection title="Liabilities" groups={['Liabilities']} lines={report.lines} />
        <div className="mt-3 flex flex-wrap justify-end gap-x-8 gap-y-1 text-sm">
          <span className="text-text-secondary">
            Total Assets <span className="font-semibold text-text-primary">{num(totals.assets)}</span>
          </span>
          <span className="text-text-secondary">
            Liabilities + Equity{' '}
            <span className="font-semibold text-text-primary">{num(bc.liabilities_plus_equity)}</span>
          </span>
        </div>
      </div>

      {/* Profit & Loss */}
      <div>
        <h4 className="mb-2 text-base font-semibold text-text-primary">Profit &amp; Loss</h4>
        <StatementSection
          title="Income &amp; Expenditure"
          groups={['Income', 'Expenditure']}
          lines={report.lines}
        />
        <div className="mt-3 flex flex-wrap justify-end gap-x-8 gap-y-1 text-sm">
          <span className="text-text-secondary">
            Total Income <span className="font-semibold text-text-primary">{num(totals.income)}</span>
          </span>
          <span className="text-text-secondary">
            Total Expenditure{' '}
            <span className="font-semibold text-text-primary">{num(totals.expenditure)}</span>
          </span>
          <span className="text-text-secondary">
            {profitLabel}{' '}
            <span
              className={cn(
                'font-semibold',
                net_profit >= 0 ? 'text-status-verified' : 'text-status-action',
              )}
            >
              {num(Math.abs(net_profit))}
            </span>
          </span>
        </div>
      </div>

      {/* Adjusting entries summary */}
      <div>
        <h4 className="mb-2 text-base font-semibold text-text-primary">Adjusting Entries Applied</h4>
        {report.entries.proposed_count > 0 && (
          <p className="mb-2 text-sm text-status-pending">
            {report.entries.proposed_count} proposed{' '}
            {report.entries.proposed_count > 1 ? 'entries are' : 'entry is'} awaiting approval and{' '}
            <strong>not</strong> reflected above.
          </p>
        )}
        {report.entries.approved.length === 0 ? (
          <p className="text-sm text-text-muted">No approved adjusting entries yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-bg-surface">
            <table className="w-full text-left text-sm text-text-secondary">
              <thead className="bg-background-subtle text-xs font-medium uppercase tracking-wider text-text-muted">
                <tr>
                  <th className="px-4 py-2">Code</th>
                  <th className="px-4 py-2">Description</th>
                  <th className="px-4 py-2 text-right">Amount</th>
                  <th className="px-4 py-2 text-right">Lines</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {report.entries.approved.map((e) => (
                  <tr key={e.id} className="hover:bg-background-subtle/30">
                    <td className="px-4 py-2 text-text-primary">{e.code || '—'}</td>
                    <td className="px-4 py-2">{e.description}</td>
                    <td className="px-4 py-2 text-right">{num(e.total)}</td>
                    <td className="px-4 py-2 text-right">{e.line_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export function ReportsTab({ engagementId }: { engagementId: string }) {
  const { data: report, isLoading } = usePreviewReport(engagementId)
  const generate = useGenerateReport()
  const toast = useToast()

  const handleGenerate = async () => {
    try {
      await generate.mutateAsync(engagementId)
      toast.success('Report generated and saved to docVault')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to generate report')
    }
  }

  const hasData = report && report.lines.length > 0

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Reports</h3>
          <p className="text-sm text-text-muted">
            Preview the Balance Sheet and P&amp;L (with approved audit adjustments applied) before
            saving the final report to docVault.
          </p>
        </div>
        <Button onClick={handleGenerate} loading={generate.isPending} disabled={!hasData}>
          Generate &amp; Save
        </Button>
      </div>

      {isLoading ? (
        <Spinner className="mx-auto mt-8 h-6 w-6" />
      ) : !hasData ? (
        <EmptyState
          title="Nothing to report yet"
          description="Import a trial balance and map its ledgers to preview the financial statements."
        />
      ) : (
        <>
          <ReportBody report={report} />
          <Card>
            <p className="text-sm text-text-secondary">
              Generated reports are saved to your <strong>docVault</strong> under the “Final Reports”
              bucket, capturing the statements exactly as previewed above.
            </p>
          </Card>
        </>
      )}
    </div>
  )
}
