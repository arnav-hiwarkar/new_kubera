import { useMemo, useState } from 'react'
import {
  Modal,
  Button,
  Field,
  Select,
  FileUploadDropzone,
  FullPageSpinner,
  useToast,
} from '@/components/ui'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/http'
import type { TBColumnMap, TBSheetInfo, TBImportResult } from '@/api/types'
import { useInspectTrialBalance, useImportTrialBalance, auditeaseKeys } from '@/api/hooks/auditease'

interface FieldDef {
  key: keyof TBColumnMap
  label: string
  required: boolean
  synonyms: string[]
}

const FIELDS: FieldDef[] = [
  { key: 'ledger_code', label: 'Ledger Code', required: false, synonyms: ['code', 'ledger code', 'gl code', 'account code'] },
  { key: 'ledger_name', label: 'Ledger Name', required: true, synonyms: ['name', 'ledger', 'ledger name', 'account', 'account name', 'particulars'] },
  { key: 'opening_balance', label: 'Opening Balance', required: true, synonyms: ['opening', 'opening balance', 'op bal', 'opening bal'] },
  { key: 'debit', label: 'Debit', required: true, synonyms: ['debit', 'dr', 'debit amount'] },
  { key: 'credit', label: 'Credit', required: true, synonyms: ['credit', 'cr', 'credit amount'] },
  { key: 'closing_balance', label: 'Closing Balance', required: true, synonyms: ['closing', 'closing balance', 'cl bal', 'balance', 'closing bal'] },
]

/** Best-effort auto-map: match each field to a header by synonym/substring. */
function guessMap(headers: string[]): Partial<TBColumnMap> {
  const norm = headers.map((h) => ({ raw: h, low: h.trim().toLowerCase() }))
  const out: Partial<TBColumnMap> = {}
  const used = new Set<string>()
  for (const f of FIELDS) {
    const hit =
      norm.find((h) => !used.has(h.raw) && f.synonyms.includes(h.low)) ??
      norm.find((h) => !used.has(h.raw) && f.synonyms.some((s) => h.low.includes(s)))
    if (hit) {
      out[f.key] = hit.raw
      used.add(hit.raw)
    }
  }
  return out
}

export function ImportTrialBalanceModal({
  open,
  onClose,
  engagementId,
}: {
  open: boolean
  onClose: () => void
  engagementId: string
}) {
  const toast = useToast()
  const qc = useQueryClient()
  const inspect = useInspectTrialBalance()
  const importTb = useImportTrialBalance()

  const [file, setFile] = useState<File | null>(null)
  const [sheets, setSheets] = useState<TBSheetInfo[]>([])
  const [sheetName, setSheetName] = useState('')
  const [map, setMap] = useState<Partial<TBColumnMap>>({})
  const [result, setResult] = useState<TBImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const activeSheet = useMemo(
    () => sheets.find((s) => s.name === sheetName) ?? sheets[0],
    [sheets, sheetName],
  )

  const reset = () => {
    setFile(null)
    setSheets([])
    setSheetName('')
    setMap({})
    setResult(null)
    setImportError(null)
    inspect.reset()
    importTb.reset()
  }

  const close = () => {
    // Force-refresh the trial balance data when closing after a successful import
    if (result && result.imported > 0) {
      qc.invalidateQueries({ queryKey: auditeaseKeys.trialBalance(engagementId) })
      qc.invalidateQueries({ queryKey: auditeaseKeys.engagement(engagementId) })
    }
    reset()
    onClose()
  }

  const onFile = async (files: File[]) => {
    const f = files[0]
    if (!f) return
    setFile(f)
    setImportError(null)
    const fd = new FormData()
    fd.append('file', f)
    try {
      const res = await inspect.mutateAsync({ engagementId, formData: fd })
      setSheets(res.sheets)
      const first = res.sheets[0]
      setSheetName(first?.name ?? '')
      setMap(guessMap(first?.headers ?? []))
    } catch (e) {
      console.error('[TB Inspect] failed:', e)
      const msg = e instanceof ApiError ? e.message : 'Could not read file'
      toast.error(msg)
      setImportError(msg)
      setFile(null)
    }
  }

  const onSheetChange = (name: string) => {
    setSheetName(name)
    const s = sheets.find((x) => x.name === name)
    setMap(guessMap(s?.headers ?? []))
  }

  const missingRequired = FIELDS.filter((f) => f.required && !map[f.key]).map((f) => f.label)
  const canImport = missingRequired.length === 0 && !!file

  const runImport = async () => {
    if (!file || !canImport) return
    setImportError(null)
    const columnMap: TBColumnMap = {
      ledger_code: map.ledger_code || null,
      ledger_name: map.ledger_name!,
      opening_balance: map.opening_balance!,
      debit: map.debit!,
      credit: map.credit!,
      closing_balance: map.closing_balance!,
    }
    const fd = new FormData()
    fd.append('file', file)
    fd.append('column_map', JSON.stringify(columnMap))
    if (sheetName) fd.append('sheet', sheetName)
    try {
      const res = await importTb.mutateAsync({ engagementId, formData: fd })
      console.log('[TB Import] success:', res.imported, 'imported,', res.skipped, 'skipped')
      setResult(res)
      // Eagerly invalidate so the TB tab is already refreshed when the user closes the modal
      qc.invalidateQueries({ queryKey: auditeaseKeys.trialBalance(engagementId) })
      toast.success(`Imported ${res.imported} ledger${res.imported === 1 ? '' : 's'}`)
    } catch (e) {
      console.error('[TB Import] failed:', e)
      const msg = e instanceof ApiError
        ? e.message
        : e instanceof Error
          ? e.message
          : 'Import failed — check the browser console for details'
      setImportError(msg)
      toast.error(msg)
    }
  }

  // --- Result view ---
  if (result) {
    return (
      <Modal
        open={open}
        onClose={close}
        title="Import complete"
        size="lg"
        footer={<Button onClick={close}>Done</Button>}
      >
        <div className="flex flex-col gap-3 text-sm">
          <div className="flex gap-6">
            <div>
              <div className="text-2xl font-semibold text-status-verified">{result.imported}</div>
              <div className="text-text-muted">imported</div>
            </div>
            <div>
              <div className="text-2xl font-semibold text-status-action">{result.skipped}</div>
              <div className="text-text-muted">skipped</div>
            </div>
          </div>
          {!result.balanced && (
            <div className="rounded-card border border-status-pending/40 badge-bg-pending px-3 py-2 text-status-pending">
              Trial balance does not balance — total debit {result.total_debit.toLocaleString()} ≠
              total credit {result.total_credit.toLocaleString()}. Imported anyway; please review.
            </div>
          )}
          {result.errors.length > 0 && (
            <div className="max-h-48 overflow-y-auto rounded-card border border-border">
              <table className="w-full text-sm">
                <thead className="bg-bg-raised/50 text-text-secondary">
                  <tr>
                    <th className="px-3 py-1.5 text-left">Row</th>
                    <th className="px-3 py-1.5 text-left">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.errors.map((err, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="px-3 py-1.5">{String((err as { row?: number }).row ?? '?')}</td>
                      <td className="px-3 py-1.5 text-text-secondary">
                        {((err as { errors?: string[] }).errors ?? []).join('; ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="Import trial balance"
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button onClick={runImport} loading={importTb.isPending} disabled={!canImport}>
            Import {activeSheet ? `(${sheetName})` : ''}
          </Button>
        </>
      }
    >
      {!file ? (
        <FileUploadDropzone
          onFilesSelected={onFile}
          accept=".csv,.xlsx"
          hint="CSV or XLSX. You'll pick the sheet and map columns next."
        />
      ) : inspect.isPending ? (
        <FullPageSpinner />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="truncate text-text-secondary">
              <span className="font-medium text-text-primary">{file.name}</span>
            </span>
            <button className="text-accent hover:underline" onClick={reset}>
              Change file
            </button>
          </div>

          {sheets.length > 1 && (
            <Field label="Sheet">
              <Select value={sheetName} onChange={(e) => onSheetChange(e.target.value)}>
                {sheets.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}

          <div>
            <p className="mb-2 text-sm font-medium text-text-secondary">Map columns</p>
            <div className="grid grid-cols-2 gap-3">
              {FIELDS.map((f) => (
                <Field key={f.key} label={f.label} required={f.required}>
                  <Select
                    value={map[f.key] ?? ''}
                    error={f.required && !map[f.key]}
                    onChange={(e) => setMap((m) => ({ ...m, [f.key]: e.target.value || undefined }))}
                  >
                    <option value="">{f.required ? '— select —' : '— none —'}</option>
                    {(activeSheet?.headers ?? []).map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </Select>
                </Field>
              ))}
            </div>
          </div>

          {activeSheet && activeSheet.preview_rows.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium text-text-secondary">Preview</p>
              <div className="max-h-40 overflow-auto rounded-card border border-border">
                <table className="w-full text-xs">
                  <thead className="bg-bg-raised/50 text-text-secondary">
                    <tr>
                      {activeSheet.headers.map((h) => (
                        <th key={h} className="whitespace-nowrap px-2 py-1 text-left">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {activeSheet.preview_rows.map((row, i) => (
                      <tr key={i} className="border-t border-border">
                        {activeSheet.headers.map((_, j) => (
                          <td key={j} className="whitespace-nowrap px-2 py-1 text-text-secondary">
                            {String(row[j] ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {missingRequired.length > 0 && (
            <p className="text-xs text-status-action">
              Map required columns: {missingRequired.join(', ')}
            </p>
          )}

          {importError && (
            <div className="rounded-card border border-status-action/40 bg-status-action/5 px-3 py-2 text-sm text-status-action">
              <strong>Error:</strong> {importError}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
