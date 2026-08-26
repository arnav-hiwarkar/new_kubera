import { useState } from 'react'
import { Button, FileUploadDropzone, Modal, Spinner, useToast } from '@/components/ui'
import { saveBlob } from '@/lib/download'
import { ApiError } from '@/api/http'
import {
  useAuditorBulkImportRequirements,
  useAuditorDownloadImportTemplate,
} from '@/api/hooks/auditorEngagements'

type RowError = { row: number; message: string }

function extractErrors(err: unknown): RowError[] {
  if (!(err instanceof ApiError)) return [{ row: 0, message: String(err) }]
  const detail = err.detail ?? err.message
  if (Array.isArray(detail)) {
    return detail.map((d) =>
      typeof d === 'object' && d !== null && 'row' in d
        ? (d as RowError)
        : { row: 0, message: String(d) },
    )
  }
  return [{ row: 0, message: String(detail) }]
}

export function BulkImportModal({
  engagementId,
  onClose,
}: {
  engagementId: string
  onClose: () => void
}) {
  const toast = useToast()
  const downloadTemplate = useAuditorDownloadImportTemplate()
  const importReqs = useAuditorBulkImportRequirements()
  const [errors, setErrors] = useState<RowError[] | null>(null)

  const handleTemplate = async () => {
    try {
      const blob = await downloadTemplate.mutateAsync(engagementId)
      saveBlob(blob, 'requirements_import_template.xlsx')
    } catch {
      toast.error('Could not download template')
    }
  }

  const handleFile = async (file: File) => {
    setErrors(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await importReqs.mutateAsync({ engagementId, formData: fd })
      toast.success(`Imported ${res.created_count} requirement${res.created_count === 1 ? '' : 's'}`)
      onClose()
    } catch (err) {
      setErrors(extractErrors(err))
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Bulk import requirements"
      size="lg"
    >
      <p className="-mt-2 mb-4 text-sm text-text-muted">
        Upload a filled template. All rows are validated first — one bad row aborts the file.
      </p>
      <div className="flex flex-col gap-4">
        <Button variant="secondary" onClick={() => void handleTemplate()} disabled={downloadTemplate.isPending}>
          {downloadTemplate.isPending ? 'Preparing…' : 'Download template (.xlsx)'}
        </Button>

        {importReqs.isPending ? (
          <Spinner className="mx-auto h-6 w-6" />
        ) : (
          <FileUploadDropzone
            accept=".xlsx,.xls,.csv"
            onFilesSelected={(files) => {
              if (files[0]) void handleFile(files[0])
            }}
            hint="Drop the filled Requirements sheet here, or click to browse"
          />
        )}

        {errors && errors.length > 0 && (
          <div className="animate-fade-in rounded-card border border-status-pending/40 bg-status-pending/10 p-3">
            <p className="mb-2 text-sm font-semibold text-text-primary">
              Nothing was imported — fix these rows and re-upload:
            </p>
            <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto text-sm text-text-secondary">
              {errors.map((e, i) => (
                <li key={i}>
                  <span className="font-semibold">Row {e.row}:</span> {e.message}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Modal>
  )
}
