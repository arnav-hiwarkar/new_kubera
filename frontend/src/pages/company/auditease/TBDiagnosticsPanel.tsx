import type { TBDiagnostics } from '@/api/types'
import { formatSigned } from '@/lib/format'

export function TBDiagnosticsPanel({ diagnostics }: { diagnostics: TBDiagnostics }) {
  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Convention" value={`${diagnostics.detected_convention} · ${diagnostics.convention_confidence}`} />
        <Metric label="Rows ready" value={String(diagnostics.rows_imported)} />
        <Metric label="Closing difference" value={formatSigned(diagnostics.closing_sum)} />
        <Metric label="Dr / Cr movement" value={`${formatSigned(diagnostics.total_debit)} / ${formatSigned(diagnostics.total_credit)}`} />
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        {diagnostics.closing_sums_to_zero && <Badge text="Closing sums to zero" ok />}
        {!diagnostics.closing_sums_to_zero && <Badge text="Closing does not sum to zero" />}
        {diagnostics.row_consistency_mismatches > 0 && <Badge text={`${diagnostics.row_consistency_mismatches} row mismatch(es)`} />}
        {diagnostics.sign_unresolved_count > 0 && <Badge text={`${diagnostics.sign_unresolved_count} unresolved sign(s)`} />}
        {diagnostics.rows_dropped_total > 0 && <Badge text={`${diagnostics.rows_dropped_total} total row(s) dropped`} ok />}
        {diagnostics.rows_error > 0 && <Badge text={`${diagnostics.rows_error} row error(s)`} />}
      </div>
      {diagnostics.issues.length > 0 && (
        <details className="rounded-card border border-border px-3 py-2">
          <summary className="cursor-pointer font-medium text-text-secondary">
            Review {diagnostics.issues.length} issue{diagnostics.issues.length === 1 ? '' : 's'}
          </summary>
          <ul className="mt-2 max-h-48 list-disc space-y-1 overflow-y-auto pl-5 text-xs text-text-secondary">
            {diagnostics.issues.map((issue, index) => (
              <li key={`${issue.row}-${index}`}>Row {issue.row}: {issue.reason}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card bg-bg-inset px-3 py-2">
      <div className="text-xs text-text-muted">{label}</div>
      <div className="mt-1 font-medium text-text-primary">{value}</div>
    </div>
  )
}

function Badge({ text, ok = false }: { text: string; ok?: boolean }) {
  return (
    <span className={`rounded-full px-2 py-1 ${ok ? 'badge-bg-verified text-status-verified' : 'badge-bg-pending text-status-pending'}`}>
      {text}
    </span>
  )
}
