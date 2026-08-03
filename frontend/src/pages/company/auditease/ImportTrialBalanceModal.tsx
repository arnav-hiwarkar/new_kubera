import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/http'
import type {
  TBColumnMap,
  TBImportResult,
  TBPreviewResponse,
  TBSheetInfo,
} from '@/api/types'
import {
  auditeaseKeys,
  useImportTrialBalance,
  useInspectTrialBalance,
  usePreviewTrialBalance,
} from '@/api/hooks/auditease'
import { Button, Field, FileUploadDropzone, FullPageSpinner, Modal, Select, useToast } from '@/components/ui'
import { formatAmount } from '@/lib/format'
import { TBDiagnosticsPanel } from './TBDiagnosticsPanel'

type Step = 'file' | 'map' | 'review' | 'done'
type MappingKey =
  | 'ledger_code' | 'ledger_name'
  | 'opening_balance' | 'opening_debit' | 'opening_credit'
  | 'debit' | 'credit'
  | 'closing_balance' | 'closing_debit' | 'closing_credit'

const FIELD_GROUPS: { title: string; fields: { key: MappingKey; label: string }[] }[] = [
  { title: 'Ledger', fields: [{ key: 'ledger_code', label: 'Ledger code' }, { key: 'ledger_name', label: 'Ledger name' }] },
  { title: 'Opening', fields: [{ key: 'opening_balance', label: 'Single opening' }, { key: 'opening_debit', label: 'Opening Dr' }, { key: 'opening_credit', label: 'Opening Cr' }] },
  { title: 'Movements', fields: [{ key: 'debit', label: 'Debit' }, { key: 'credit', label: 'Credit' }] },
  { title: 'Closing', fields: [{ key: 'closing_balance', label: 'Single closing' }, { key: 'closing_debit', label: 'Closing Dr' }, { key: 'closing_credit', label: 'Closing Cr' }] },
]

const FALLBACK_SYNONYMS: Partial<Record<MappingKey, string[]>> = {
  ledger_code: ['code', 'ledger code', 'gl code'],
  ledger_name: ['name', 'ledger', 'ledger name', 'particulars'],
  opening_balance: ['opening', 'opening balance'],
  debit: ['debit', 'dr'], credit: ['credit', 'cr'],
  closing_balance: ['closing', 'closing balance', 'balance'],
}

function fallbackMap(headers: string[]): Partial<TBColumnMap> {
  const result: Partial<TBColumnMap> = {}
  for (const [key, synonyms] of Object.entries(FALLBACK_SYNONYMS) as [MappingKey, string[]][]) {
    const hit = headers.find((header) => synonyms.includes(header.trim().toLowerCase()))
    if (hit) result[key] = hit
  }
  return result
}

function apiMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.detail && typeof error.detail === 'object' && 'message' in error.detail) {
      return String((error.detail as { message: unknown }).message)
    }
    return error.message
  }
  return error instanceof Error ? error.message : 'Import failed'
}

export function ImportTrialBalanceModal({ open, onClose, engagementId }: {
  open: boolean
  onClose: () => void
  engagementId: string
}) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const inspect = useInspectTrialBalance()
  const previewMutation = usePreviewTrialBalance()
  const importMutation = useImportTrialBalance()
  const [step, setStep] = useState<Step>('file')
  const [file, setFile] = useState<File | null>(null)
  const [sheets, setSheets] = useState<TBSheetInfo[]>([])
  const [sheetName, setSheetName] = useState('')
  const [map, setMap] = useState<Partial<TBColumnMap>>({ decimal_style: 'auto', credit_sign: 'auto' })
  const [convention, setConvention] = useState<'' | 'signed' | 'magnitude'>('')
  const [preview, setPreview] = useState<TBPreviewResponse | null>(null)
  const [result, setResult] = useState<TBImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const activeSheet = useMemo(
    () => sheets.find((sheet) => sheet.name === sheetName) ?? sheets[0],
    [sheets, sheetName],
  )

  const mappingProblems = useMemo(() => {
    const problems: string[] = []
    if (!map.ledger_name) problems.push('Map Ledger name')
    const openingPairPartial = Boolean(map.opening_debit) !== Boolean(map.opening_credit)
    const closingPairPartial = Boolean(map.closing_debit) !== Boolean(map.closing_credit)
    if (openingPairPartial) problems.push('Opening Dr and Cr must both be mapped')
    if (closingPairPartial) problems.push('Closing Dr and Cr must both be mapped')
    const hasBalance = Boolean(
      map.closing_balance
      || (map.closing_debit && map.closing_credit)
      || (map.debit && map.credit),
    )
    if (!hasBalance) problems.push('Map a closing balance, closing Dr/Cr pair, or Debit/Credit pair')
    return problems
  }, [map])

  const reset = () => {
    setStep('file'); setFile(null); setSheets([]); setSheetName('')
    setMap({ decimal_style: 'auto', credit_sign: 'auto' })
    setConvention(''); setPreview(null); setResult(null); setError(null)
    inspect.reset(); previewMutation.reset(); importMutation.reset()
  }

  const close = () => {
    if (result?.imported) {
      queryClient.invalidateQueries({ queryKey: auditeaseKeys.trialBalance(engagementId) })
      queryClient.invalidateQueries({ queryKey: auditeaseKeys.engagement(engagementId) })
    }
    reset()
    onClose()
  }

  const applySheet = (sheet: TBSheetInfo | undefined) => {
    if (!sheet) return
    setSheetName(sheet.name)
    const suggested = Object.keys(sheet.suggested_map).length
      ? sheet.suggested_map as Partial<TBColumnMap>
      : fallbackMap(sheet.headers)
    setMap({ ...suggested, decimal_style: 'auto', credit_sign: 'auto' })
  }

  const onFile = async (files: File[]) => {
    const selected = files[0]
    if (!selected) return
    setFile(selected); setError(null)
    const formData = new FormData(); formData.append('file', selected)
    try {
      const response = await inspect.mutateAsync({ engagementId, formData })
      setSheets(response.sheets)
      applySheet(response.sheets[0])
      setStep('map')
    } catch (caught) {
      setFile(null)
      const message = apiMessage(caught); setError(message); toast.error(message)
    }
  }

  const columnMap = (): TBColumnMap => ({
    ledger_code: map.ledger_code || null,
    ledger_name: map.ledger_name!,
    opening_balance: map.opening_balance || null,
    opening_debit: map.opening_debit || null,
    opening_credit: map.opening_credit || null,
    debit: map.debit || null,
    credit: map.credit || null,
    closing_balance: map.closing_balance || null,
    closing_debit: map.closing_debit || null,
    closing_credit: map.closing_credit || null,
    decimal_style: map.decimal_style ?? 'auto',
    credit_sign: map.credit_sign ?? 'auto',
  })

  const formData = (confirm = false) => {
    const data = new FormData()
    data.append('file', file!)
    data.append('column_map', JSON.stringify(columnMap()))
    if (sheetName) data.append('sheet', sheetName)
    if (activeSheet?.header_row) data.append('header_row', String(activeSheet.header_row))
    if (convention) data.append('sign_convention', convention)
    if (confirm) data.append('confirm', 'true')
    return data
  }

  const runPreview = async () => {
    if (!file || mappingProblems.length) return
    setError(null)
    try {
      const response = await previewMutation.mutateAsync({ engagementId, formData: formData() })
      setPreview(response); setStep('review')
    } catch (caught) {
      const message = apiMessage(caught); setError(message); toast.error(message)
    }
  }

  const runImport = async () => {
    if (!preview) return
    setError(null)
    try {
      const confirm = preview.reimport_impact?.requires_confirmation ?? false
      const response = await importMutation.mutateAsync({ engagementId, formData: formData(confirm) })
      setResult(response); setStep('done')
      toast.success(`Imported ${response.imported} ledger${response.imported === 1 ? '' : 's'}`)
    } catch (caught) {
      const message = apiMessage(caught); setError(message); toast.error(message)
    }
  }

  const footer = step === 'file' ? <Button variant="secondary" onClick={close}>Cancel</Button>
    : step === 'map' ? <>
        <Button variant="secondary" onClick={reset}>Change file</Button>
        <Button onClick={runPreview} loading={previewMutation.isPending} disabled={mappingProblems.length > 0}>Check &amp; preview</Button>
      </>
    : step === 'review' ? <>
        <Button variant="secondary" onClick={() => setStep('map')}>Back to mapping</Button>
        <Button onClick={runImport} loading={importMutation.isPending}>Import anyway</Button>
      </>
    : <Button onClick={close}>Done</Button>

  return (
    <Modal open={open} onClose={close} title={step === 'done' ? 'Import complete' : 'Import trial balance'} size="lg" footer={footer}>
      {step === 'file' && !inspect.isPending && (
        <FileUploadDropzone onFilesSelected={onFile} accept=".csv,.xlsx" hint="CSV or XLSX. You will map and review it before anything is written." />
      )}
      {inspect.isPending && <FullPageSpinner />}
      {step === 'map' && activeSheet && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between text-sm"><strong>{file?.name}</strong><span className="text-text-muted">Header row {activeSheet.header_row}</span></div>
          {sheets.length > 1 && <Field label="Sheet"><Select value={sheetName} onChange={(event) => applySheet(sheets.find((sheet) => sheet.name === event.target.value))}>{sheets.map((sheet) => <option key={sheet.name}>{sheet.name}</option>)}</Select></Field>}
          {FIELD_GROUPS.map((group) => (
            <div key={group.title}>
              <p className="mb-2 text-sm font-medium text-text-secondary">{group.title}</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {group.fields.map((field) => <Field key={field.key} label={field.label} required={field.key === 'ledger_name'}><Select value={String(map[field.key] ?? '')} onChange={(event) => setMap((current) => ({ ...current, [field.key]: event.target.value || null }))}><option value="">— none —</option>{activeSheet.headers.map((header) => <option key={header} value={header}>{header}</option>)}</Select></Field>)}
              </div>
            </div>
          ))}
          <details className="rounded-card border border-border px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium text-text-secondary">Number format</summary>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Field label="Decimal style"><Select value={map.decimal_style ?? 'auto'} onChange={(event) => setMap((current) => ({ ...current, decimal_style: event.target.value as TBColumnMap['decimal_style'] }))}><option value="auto">Auto detect</option><option value="dot">Dot decimal</option><option value="comma">Comma decimal</option></Select></Field>
              <Field label="Legacy credit sign"><Select value={map.credit_sign ?? 'auto'} onChange={(event) => setMap((current) => ({ ...current, credit_sign: event.target.value as TBColumnMap['credit_sign'] }))}><option value="auto">Auto detect</option><option value="negative">Credits negative</option><option value="positive">Credits positive</option></Select></Field>
              <Field label="Convention override"><Select value={convention} onChange={(event) => setConvention(event.target.value as typeof convention)}><option value="">Auto detect</option><option value="signed">Signed balances</option><option value="magnitude">All-positive balances</option></Select></Field>
            </div>
          </details>
          {mappingProblems.length > 0 && <ul className="list-disc pl-5 text-xs text-status-action">{mappingProblems.map((problem) => <li key={problem}>{problem}</li>)}</ul>}
        </div>
      )}
      {step === 'review' && preview && (
        <div className="flex flex-col gap-4">
          <TBDiagnosticsPanel diagnostics={preview.diagnostics} />
          {preview.reimport_impact && (
            <div className="rounded-card border border-border px-3 py-2 text-sm text-text-secondary">
              Re-import: {preview.reimport_impact.matched_by_code + preview.reimport_impact.matched_by_name} matched, {preview.reimport_impact.new_ledger_count} new, {preview.reimport_impact.retained_referenced.length} retained.
              {preview.reimport_impact.will_lose_mapping.length > 0 && <div className="mt-1 text-status-pending">Mappings removed: {preview.reimport_impact.will_lose_mapping.join(', ')}</div>}
              {preview.reimport_impact.ambiguous_matches.length > 0 && <div className="mt-1 text-status-pending">Ambiguous: {preview.reimport_impact.ambiguous_matches.join(', ')}</div>}
            </div>
          )}
          <div className="max-h-52 overflow-auto rounded-card border border-border">
            <table className="w-full text-xs"><thead className="bg-bg-inset text-text-muted"><tr><th className="px-2 py-1 text-left">Row</th><th className="px-2 py-1 text-left">Ledger</th><th className="px-2 py-1 text-right">Opening</th><th className="px-2 py-1 text-right">Debit</th><th className="px-2 py-1 text-right">Credit</th><th className="px-2 py-1 text-right">Closing</th></tr></thead><tbody>{preview.sample_rows.map((row) => <tr key={row.row} className="border-t border-border"><td className="px-2 py-1">{row.row}</td><td className="px-2 py-1">{row.ledger_name}</td><td className="px-2 py-1 text-right">{formatAmount(row.opening_balance, { style: 'drcr' })}</td><td className="px-2 py-1 text-right">{formatAmount(row.debit, { style: 'signed' })}</td><td className="px-2 py-1 text-right">{formatAmount(row.credit, { style: 'signed' })}</td><td className="px-2 py-1 text-right">{formatAmount(row.closing_net_debit, { style: 'drcr' })}</td></tr>)}</tbody></table>
          </div>
        </div>
      )}
      {step === 'done' && result && <div className="flex flex-col gap-4"><div className="text-sm text-text-secondary"><strong className="text-status-verified">{result.imported}</strong> imported · <strong>{result.skipped}</strong> skipped</div>{result.diagnostics && <TBDiagnosticsPanel diagnostics={result.diagnostics} />}</div>}
      {error && <div className="mt-3 rounded-card border border-status-action/40 bg-status-action/5 px-3 py-2 text-sm text-status-action">{error}</div>}
    </Modal>
  )
}
