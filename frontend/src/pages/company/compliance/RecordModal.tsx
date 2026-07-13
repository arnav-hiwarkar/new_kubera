import { useEffect, useMemo, useState } from 'react'
import { Modal, Button, Field, Input, Select, useToast } from '@/components/ui'
import { docvaultApi } from '@/api/endpoints/docvault'
import { saveBlob } from '@/lib/download'
import { useCreateMeetingRecord, type Domain } from '@/api/hooks/compliance'
import type { DocumentTypeResponse } from '@/api/types'
import { readFields } from './schema'
import { resolveBucket } from './buckets'

function todayIso(): string {
  const now = new Date()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${mm}-${dd}`
}

interface RecordModalProps {
  open: boolean
  onClose: () => void
  domain: Domain
  types: DocumentTypeResponse[]
}

export function RecordModal({ open, onClose, domain, types }: RecordModalProps) {
  const toast = useToast()
  const create = useCreateMeetingRecord(domain)

  const [typeId, setTypeId] = useState('')
  const [recordDate, setRecordDate] = useState(todayIso())
  const [values, setValues] = useState<Record<string, string>>({})
  const [file, setFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setTypeId('')
    setRecordDate(todayIso())
    setValues({})
    setFile(null)
    setSaving(false)
  }, [open])

  const selectedType = useMemo(() => types.find((t) => t.id === typeId) ?? null, [types, typeId])
  const fields = useMemo(() => readFields(selectedType?.metadata_schema), [selectedType])

  const setValue = (key: string, val: string) => setValues((v) => ({ ...v, [key]: val }))

  const downloadTemplate = async () => {
    if (!selectedType?.template_file_id) return
    try {
      const blob = await docvaultApi.downloadDocument(selectedType.template_file_id)
      saveBlob(blob, `${selectedType.name}-template`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to download template')
    }
  }

  const handleSubmit = async () => {
    if (!selectedType) return toast.error('Select a document type')
    for (const f of fields) {
      if (f.required && !values[f.key]?.trim()) {
        return toast.error(`${f.label} is required`)
      }
    }
    if (!file) return toast.error('Attach the completed document')

    setSaving(true)
    try {
      const bucketId = await resolveBucket(domain === 'roc' ? 'ROC Compliance' : 'SecretarialEase')
      const fd = new FormData()
      fd.append('title', `${selectedType.name} ${recordDate}`.trim())
      fd.append('file', file)
      fd.append('bucket_id', bucketId)
      const doc = await docvaultApi.uploadDocument(fd)

      const structured: Record<string, string> = {}
      for (const f of fields) {
        const v = values[f.key]?.trim()
        if (v) structured[f.key] = v
      }

      await create.mutateAsync({
        doc_type_id: selectedType.id,
        document_id: doc.id,
        structured_metadata: structured,
        record_date: recordDate || null,
      })
      toast.success('Record created')
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to create record')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New record"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={saving}>
            Create
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Document type" required>
          <Select value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            <option value="">— Select —</option>
            {types.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </Field>

        {selectedType?.template_file_id && (
          <button
            type="button"
            onClick={downloadTemplate}
            className="self-start text-sm font-medium text-accent hover:underline"
          >
            Download template
          </button>
        )}

        {fields.map((f) => (
          <Field key={f.key} label={f.label} required={f.required}>
            {f.type === 'dropdown' ? (
              <Select value={values[f.key] ?? ''} onChange={(e) => setValue(f.key, e.target.value)}>
                <option value="">— Select —</option>
                {(f.options ?? []).map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                type={f.type === 'number' ? 'number' : f.type === 'date' ? 'date' : 'text'}
                value={values[f.key] ?? ''}
                onChange={(e) => setValue(f.key, e.target.value)}
              />
            )}
          </Field>
        ))}

        <Field label="Record date">
          <Input type="date" value={recordDate} onChange={(e) => setRecordDate(e.target.value)} />
        </Field>

        <Field label="Completed document" required hint="Upload the filled-in document">
          <input
            type="file"
            className="mt-1 block w-full text-sm text-text-secondary file:mr-3 file:rounded-btn file:border file:border-border file:bg-bg-raised file:px-3 file:py-1.5 file:text-sm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Field>
      </div>
    </Modal>
  )
}
