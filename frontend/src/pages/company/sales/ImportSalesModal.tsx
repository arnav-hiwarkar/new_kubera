import { useState } from 'react'
import { Modal, Button, Select, useToast } from '@/components/ui'
import { useInspectSalesImport, useImportSales } from '@/api/hooks/sales'
import type { SalesSheetInfo, CustomFieldResponse, ImportResult } from '@/api/types'

interface ImportSalesModalProps {
  open: boolean
  onClose: () => void
  activeFields: CustomFieldResponse[]
}

type Target = { key: string; label: string; required?: boolean }

const BASE_TARGETS: Target[] = [
  { key: 'client_name', label: 'Client name', required: true },
  { key: 'product_service', label: 'Product / service', required: true },
  { key: 'amount', label: 'Amount', required: true },
  { key: 'status', label: 'Status' },
]

const SKIP = ''

export function ImportSalesModal({ open, onClose, activeFields }: ImportSalesModalProps) {
  const toast = useToast()
  const inspect = useInspectSalesImport()
  const runImport = useImportSales()

  const [file, setFile] = useState<File | null>(null)
  const [sheet, setSheet] = useState<SalesSheetInfo | null>(null)
  const [mappings, setMappings] = useState<Record<string, string>>({})
  const [result, setResult] = useState<ImportResult | null>(null)

  const targets: Target[] = [
    ...BASE_TARGETS,
    ...activeFields.map((f) => ({ key: f.field_key, label: f.field_name, required: f.is_required })),
  ]

  const reset = () => {
    setFile(null)
    setSheet(null)
    setMappings({})
    setResult(null)
  }
  const close = () => {
    reset()
    onClose()
  }

  const onPickFile = async (f: File) => {
    setFile(f)
    setSheet(null)
    setResult(null)
    const fd = new FormData()
    fd.append('file', f)
    try {
      const res = await inspect.mutateAsync(fd)
      const first = res.sheets[0] ?? null
      setSheet(first)
      // Auto-map exact header matches to speed things up.
      if (first) {
        const auto: Record<string, string> = {}
        for (const t of targets) {
          const hit = first.headers.find((h) => h.toLowerCase() === t.label.toLowerCase() || h.toLowerCase() === t.key.toLowerCase())
          if (hit) auto[t.key] = hit
        }
        setMappings(auto)
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not read file')
    }
  }

  const canImport = !!file && !!mappings.client_name && !!mappings.product_service && !!mappings.amount

  const doImport = async () => {
    if (!file) return
    const pairs = Object.entries(mappings)
      .filter(([, src]) => src)
      .map(([target, src]) => ({ source_column: src, target_field: target }))
    const fd = new FormData()
    fd.append('file', file)
    fd.append('mappings', JSON.stringify(pairs))
    try {
      const res = await runImport.mutateAsync(fd)
      setResult(res)
      if (res.imported > 0) toast.success(`Imported ${res.imported} sale(s)`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Import failed')
    }
  }

  const footer =
    result != null ? (
      <Button onClick={close}>Done</Button>
    ) : (
      <>
        <Button variant="ghost" onClick={close}>Cancel</Button>
        <Button onClick={doImport} loading={runImport.isPending} disabled={!canImport}>
          Import
        </Button>
      </>
    )

  return (
    <Modal open={open} onClose={close} title="Import sales" footer={footer} size="lg">
      {result != null ? (
        <div className="flex flex-col gap-3">
          <div className="flex gap-6 text-sm">
            <span className="text-status-verified">Imported: <strong>{result.imported}</strong></span>
            <span className="text-status-pending">Skipped: <strong>{result.skipped}</strong></span>
          </div>
          {result.errors.length > 0 && (
            <div className="max-h-64 overflow-y-auto rounded-card border border-border">
              <table className="w-full text-left text-sm">
                <thead className="bg-background-subtle text-xs uppercase text-text-muted">
                  <tr>
                    <th className="px-3 py-2">Row</th>
                    <th className="px-3 py-2">Errors</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {result.errors.map((row, i) => {
                    const rowNum = String((row as { row?: unknown }).row ?? i + 1)
                    const msgsRaw = (row as { errors?: unknown }).errors
                    const msgs = Array.isArray(msgsRaw) ? msgsRaw.map(String) : [String(msgsRaw)]
                    return (
                      <tr key={rowNum + '-' + i}>
                        <td className="px-3 py-2 align-top text-text-secondary">{rowNum}</td>
                        <td className="px-3 py-2 text-status-action">{msgs.join('; ')}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div>
            <label className="text-sm font-medium text-text-secondary">Spreadsheet (.csv / .xlsx)</label>
            <input
              type="file"
              accept=".csv,.xlsx"
              className="mt-1 block w-full text-sm text-text-secondary file:mr-3 file:rounded-btn file:border file:border-border file:bg-bg-raised file:px-3 file:py-1.5 file:text-sm"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void onPickFile(f)
              }}
            />
          </div>

          {inspect.isPending && <p className="text-sm text-text-muted">Reading file…</p>}

          {sheet && (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-text-secondary">
                Map your columns. <span className="text-status-action">*</span> required.
              </p>
              <div className="rounded-card border border-border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-background-subtle text-xs uppercase text-text-muted">
                    <tr>
                      <th className="px-3 py-2">Field</th>
                      <th className="px-3 py-2">Source column</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {targets.map((t) => (
                      <tr key={t.key}>
                        <td className="px-3 py-2 text-text-primary">
                          {t.label}
                          {t.required && <span className="text-status-action"> *</span>}
                        </td>
                        <td className="px-3 py-2">
                          <Select
                            value={mappings[t.key] ?? SKIP}
                            onChange={(e) => setMappings((m) => ({ ...m, [t.key]: e.target.value }))}
                          >
                            <option value={SKIP}>— skip —</option>
                            {sheet.headers.map((h) => (
                              <option key={h} value={h}>{h}</option>
                            ))}
                          </Select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!canImport && (
                <p className="text-xs text-status-action">Map at least Client name, Product / service and Amount to import.</p>
              )}
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
