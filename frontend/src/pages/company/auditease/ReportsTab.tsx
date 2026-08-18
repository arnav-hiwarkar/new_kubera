import { useState } from 'react'
import { Card, Button, Spinner, useToast, EmptyState } from '@/components/ui'
import { usePreviewReport, useGenerateReport, usePreviewReportHtml, useArchiveEngagementReport } from '@/api/hooks/auditease'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import { formatMoney } from '@/lib/format'
import { saveBlob } from '@/lib/download'
import { cn } from '@/lib/cn'
import { ReportExportMenu } from '@/components/reports/ReportExportMenu'
import type { ReportLine, ReportPreviewResponse } from '@/api/types'
import { FileSpreadsheet, FileText, Archive } from 'lucide-react'

const REPORT_OPTIONS = [
  { key: 'balance_sheet', label: '1. Balance Sheet' },
  { key: 'profit_and_loss', label: '2. Profit & Loss' },
  { key: 'notes_to_accounts', label: '3. Notes' },
  { key: 'trial_balance_detailed', label: '4. TB (Detailed)' },
  { key: 'trial_balance_summary', label: '5. TB (Summary)' },
  { key: 'extended_trial_balance', label: '6. Extended TB' },
  { key: 'adjusting_entries', label: '7. Adjusting Entries' },
  { key: 'ledger_mapping', label: '8. Mapping' },
  { key: 'exceptions', label: '9. Exceptions' },
] as const

const UNIT_OPTIONS = [
  { key: 'absolute', label: 'Absolute (₹)' },
  { key: 'thousands', label: "Thousands (₹ '000)" },
  { key: 'lakhs', label: 'Lakhs (₹ Lakhs)' },
  { key: 'crores', label: 'Crores (₹ Cr)' },
] as const

const num = (v: number) => <span className="tabular-nums">{formatMoney(v)}</span>

function StatementSection({
  title,
  rows,
  subtotal,
}: {
  title: string
  rows: ReportLine[]
  subtotal: number
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-bg-surface">
      <table className="w-full text-left text-sm text-text-secondary">
        <thead className="bg-bg-inset text-xs font-medium uppercase tracking-wider text-text-muted">
          <tr>
            <th className="px-4 py-2">Ledger</th>
            <th className="px-4 py-2 text-right">Closing</th>
            <th className="px-4 py-2 text-right">Adjustment</th>
            <th className="px-4 py-2 text-right">Final</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rows.length > 0 && <ReportGroupBlock group={title} rows={rows} subtotal={subtotal} />}
        </tbody>
      </table>
      <div className="border-t border-border px-4 py-2 text-right text-sm font-semibold text-text-primary">
        {title} total {num(subtotal)}
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
      <tr className="bg-bg-inset/50">
        <td className="px-4 py-2 font-semibold text-text-primary" colSpan={3}>
          {group}
        </td>
        <td className="px-4 py-2 text-right font-semibold text-text-primary">{num(subtotal)}</td>
      </tr>
      {rows.map((r) => {
        const subPath = (r.group_path ?? []).slice(1).join(' › ')
        return (
          <tr key={r.ledger_id ?? `synthetic-${r.ledger_name}`} className={cn('hover:bg-bg-inset/30', r.is_synthetic && 'bg-bg-inset/30 italic')}>
            <td className="px-4 py-2 pl-8">
              <div className="font-medium text-text-primary">{r.ledger_name}</div>
              {subPath && <div className="text-xs text-text-muted">{subPath}</div>}
            </td>
            <td className="px-4 py-2 text-right">{r.is_synthetic ? '—' : num(r.closing)}</td>
            <td
              className={cn(
                'px-4 py-2 text-right',
                r.adjustment !== 0 && 'font-medium text-status-submitted',
              )}
            >
              {!r.is_synthetic && r.adjustment !== 0 ? num(r.adjustment) : '—'}
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
  const equityNames = new Set([
    'share capital', 'reserves & surplus', 'reserves and surplus',
    'money received against share warrants', 'share application money pending allotment',
  ])
  const assetRows = report.lines.filter((line) => line.top_group === 'Assets')
  const incomeRows = report.lines.filter((line) => line.top_group === 'Income')
  const expenseRows = report.lines.filter((line) => line.top_group === 'Expenditure')
  const equityRows = report.lines.filter((line) =>
    line.top_group === 'Liabilities'
    && !!line.group_path?.[1]
    && equityNames.has(line.group_path[1].toLowerCase()),
  )
  const liabilityRows = report.lines.filter((line) =>
    line.top_group === 'Liabilities' && !equityRows.includes(line),
  )

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={cn(
            'inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-medium',
            bc.balanced
              ? 'text-status-verified badge-bg-verified'
              : 'text-status-action badge-bg-action',
          )}
        >
          {!bc.statement_ready
            ? '● Needs mapping or sign review'
            : bc.balanced
              ? '● Balanced'
              : `● Not balanced — difference ${formatMoney(bc.difference)}`}
        </span>
        {report.unmapped_count > 0 && (
          <span className="rounded-md bg-status-pending/10 px-3 py-1 text-sm text-status-pending">
            {report.unmapped_count} unmapped ledger{report.unmapped_count > 1 ? 's' : ''} excluded from
            these statements
          </span>
        )}
      </div>
      {report.warnings.length > 0 && (
        <div className="rounded-card border border-status-pending/30 bg-status-pending/5 px-4 py-3 text-sm text-status-pending">
          <ul className="list-disc space-y-1 pl-5">
            {report.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </div>
      )}

      <div>
        <h4 className="mb-2 text-base font-semibold text-text-primary">Balance Sheet</h4>
        <StatementSection title="Assets" rows={assetRows} subtotal={totals.assets} />
        <div className="h-3" />
        <StatementSection title="Other Liabilities" rows={liabilityRows} subtotal={totals.other_liabilities} />
        <div className="h-3" />
        <StatementSection title="Equity" rows={equityRows} subtotal={totals.equity} />
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

      <div>
        <h4 className="mb-2 text-base font-semibold text-text-primary">Profit &amp; Loss</h4>
        <StatementSection title="Income" rows={incomeRows} subtotal={totals.income} />
        <div className="h-3" />
        <StatementSection title="Expenditure" rows={expenseRows} subtotal={totals.expenditure} />
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
              <thead className="bg-bg-inset text-xs font-medium uppercase tracking-wider text-text-muted">
                <tr>
                  <th className="px-4 py-2">Code</th>
                  <th className="px-4 py-2">Description</th>
                  <th className="px-4 py-2 text-right">Amount</th>
                  <th className="px-4 py-2 text-right">Lines</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {report.entries.approved.map((e) => (
                  <tr key={e.id} className="hover:bg-bg-inset/30">
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
  const [selectedReport, setSelectedReport] = useState<string>('balance_sheet')
  const [selectedUnits, setSelectedUnits] = useState<string>('absolute')
  const [viewMode, setViewMode] = useState<'statutory' | 'breakdown'>('breakdown')

  const { data: report, isLoading } = usePreviewReport(engagementId)
  const { data: htmlPreview, isLoading: isHtmlLoading } = usePreviewReportHtml(engagementId, selectedReport, selectedUnits)
  const generate = useGenerateReport()
  const archive = useArchiveEngagementReport()
  const toast = useToast()

  const handleExportSingle = async (format: 'xlsx' | 'pdf') => {
    try {
      const blob = await auditeaseCompanyApi.exportReport(engagementId, selectedReport, format, selectedUnits)
      saveBlob(blob, `${selectedReport}_${selectedUnits}.${format}`)
      toast.success(`Downloaded ${selectedReport}.${format}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to export ${format.toUpperCase()}`)
    }
  }

  const handleArchiveSingle = async () => {
    try {
      await archive.mutateAsync({
        engagementId,
        reportKey: selectedReport,
        format: 'pdf',
        units: selectedUnits,
      })
      toast.success(`Saved ${selectedReport} to docVault (Final Reports)`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to archive report')
    }
  }

  const handleExportPack = async (format: 'xlsx' | 'pdf') => {
    try {
      const blob = await auditeaseCompanyApi.exportReportPack(engagementId, format, selectedUnits)
      saveBlob(blob, `Audited_Financial_Statements_Pack_${selectedUnits}.${format}`)
      toast.success(`Downloaded Financial Statements Pack (.${format})`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to download pack')
    }
  }

  const handleArchivePack = async () => {
    try {
      await archive.mutateAsync({
        engagementId,
        reportKey: 'pack',
        format: 'pdf',
        units: selectedUnits,
      })
      toast.success('Saved complete Report Pack to docVault (Final Reports)')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to archive report pack')
    }
  }

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
      {/* Top Header & Global Actions */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Statutory Reports &amp; Financial Statements</h3>
          <p className="text-sm text-text-muted">
            Preview, format, export, and archive Schedule III statements and audit schedules.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Legacy Generate & Save button maintained for test backwards compatibility */}
          <Button onClick={handleGenerate} loading={generate.isPending} disabled={!hasData} variant="secondary" size="sm">
            Generate &amp; Save
          </Button>

          {/* Combined Pack Actions */}
          <div className="flex items-center gap-1.5 rounded-lg border border-border bg-bg-surface p-1 shadow-sm">
            <button
              type="button"
              disabled={!hasData}
              onClick={() => handleExportPack('xlsx')}
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold text-text-secondary hover:bg-bg-raised hover:text-text-primary disabled:opacity-50"
              title="Download full multi-sheet Excel pack"
            >
              <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-600" />
              <span>Pack (.xlsx)</span>
            </button>
            <button
              type="button"
              disabled={!hasData}
              onClick={() => handleExportPack('pdf')}
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold text-text-secondary hover:bg-bg-raised hover:text-text-primary disabled:opacity-50"
              title="Download combined statutory PDF pack"
            >
              <FileText className="h-3.5 w-3.5 text-rose-600" />
              <span>Pack (.pdf)</span>
            </button>
            <button
              type="button"
              disabled={!hasData}
              onClick={handleArchivePack}
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold text-text-secondary hover:bg-bg-raised hover:text-text-primary disabled:opacity-50"
              title="Archive full pack to docVault"
            >
              <Archive className="h-3.5 w-3.5 text-amber-600" />
              <span>Save Pack</span>
            </button>
          </div>
        </div>
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
          {/* Controls Bar: Report Selector, Units, View Mode, Active Report Export */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-bg-surface p-3 shadow-sm">
            {/* Report Selector */}
            <div className="flex flex-wrap items-center gap-1">
              {REPORT_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => setSelectedReport(opt.key)}
                  className={cn(
                    'rounded-btn px-2.5 py-1.5 text-xs font-semibold transition-colors',
                    selectedReport === opt.key
                      ? 'bg-accent text-accent-contrast shadow-sm'
                      : 'text-text-secondary hover:bg-bg-raised hover:text-text-primary',
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* Units & Export Dropdown */}
            <div className="flex items-center gap-2">
              <select
                aria-label="Currency Units"
                value={selectedUnits}
                onChange={(e) => setSelectedUnits(e.target.value)}
                className="h-8 rounded-btn border border-border-strong bg-bg-surface px-2.5 text-xs font-medium text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
              >
                {UNIT_OPTIONS.map((u) => (
                  <option key={u.key} value={u.key}>
                    {u.label}
                  </option>
                ))}
              </select>

              <div className="flex items-center rounded-btn border border-border bg-bg-inset p-0.5">
                <button
                  type="button"
                  onClick={() => setViewMode('statutory')}
                  className={cn(
                    'rounded-md px-2 py-1 text-xs font-semibold transition-colors',
                    viewMode === 'statutory'
                      ? 'bg-bg-surface text-text-primary shadow-xs'
                      : 'text-text-muted hover:text-text-secondary',
                  )}
                >
                  Statutory
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode('breakdown')}
                  className={cn(
                    'rounded-md px-2 py-1 text-xs font-semibold transition-colors',
                    viewMode === 'breakdown'
                      ? 'bg-bg-surface text-text-primary shadow-xs'
                      : 'text-text-muted hover:text-text-secondary',
                  )}
                >
                  Ledger View
                </button>
              </div>

              <ReportExportMenu
                onExportExcel={() => handleExportSingle('xlsx')}
                onExportPdf={() => handleExportSingle('pdf')}
                onArchiveDocVault={handleArchiveSingle}
              />
            </div>
          </div>

          {/* Main Preview Area */}
          {viewMode === 'statutory' ? (
            <div className="rounded-card border border-border bg-bg-surface p-6 shadow-sm">
              {isHtmlLoading ? (
                <div className="flex h-64 items-center justify-center">
                  <Spinner className="h-6 w-6 text-accent" />
                </div>
              ) : htmlPreview?.html ? (
                <div
                  className="report-preview-html prose max-w-none dark:prose-invert"
                  dangerouslySetInnerHTML={{ __html: htmlPreview.html }}
                />
              ) : (
                <ReportBody report={report} />
              )}
            </div>
          ) : (
            <ReportBody report={report} />
          )}

          <Card>
            <p className="text-sm text-text-secondary">
              Generated reports and packs are saved to your <strong>docVault</strong> under the “Final Reports”
              bucket, encrypted and available for audit sign-off.
            </p>
          </Card>
        </>
      )}
    </div>
  )
}
