import { useEffect, useMemo, useState } from 'react'
import { Modal, Button, Field, Input, Select, useToast } from '@/components/ui'
import { docvaultApi } from '@/api/endpoints/docvault'
import { saveBlob } from '@/lib/download'
import {
  apiFor,
  useCreateMeetingRecord,
  useUpdateMeetingRecord,
  type Domain,
} from '@/api/hooks/compliance'
import type { DocumentTypeResponse, MeetingRecordResponse } from '@/api/types'
import { readFields } from './schema'

function todayIso(): string {
  const now = new Date()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${mm}-${dd}`
}

/** Read structured_metadata back into the string map the form edits. */
function readValues(metadata: unknown): Record<string, string> {
  const raw = metadata as Record<string, unknown> | null
  if (!raw || typeof raw !== 'object') return {}
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(raw)) {
    if (v != null) out[k] = String(v)
  }
  return out
}

interface RecordModalProps {
  open: boolean
  onClose: () => void
  domain: Domain
  types: DocumentTypeResponse[]
  /** Present when editing an existing record; absent when creating a new one. */
  record?: MeetingRecordResponse | null
}

export function RecordModal({ open, onClose, domain, types, record }: RecordModalProps) {
  const toast = useToast()
  const create = useCreateMeetingRecord(domain)
  const update = useUpdateMeetingRecord(domain)
  const isEdit = Boolean(record)

  const [typeId, setTypeId] = useState('')
  const [title, setTitle] = useState('')
  const [titleTouched, setTitleTouched] = useState(false)
  const [recordDate, setRecordDate] = useState(todayIso())
  const [values, setValues] = useState<Record<string, string>>({})
  const [file, setFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setTypeId(record?.doc_type_id ?? '')
    setTitle(record?.title ?? '')
    setTitleTouched(Boolean(record?.title))
    setRecordDate(record?.record_date ?? todayIso())
    setValues(readValues(record?.structured_metadata))
    setFile(null)
    setSaving(false)
  }, [open, record])

  const selectedType = useMemo(() => types.find((t) => t.id === typeId) ?? null, [types, typeId])
  const fields = useMemo(() => readFields(selectedType?.metadata_schema), [selectedType])

  // Keep the old derived-title behaviour as a default, but stop overwriting once
  // the user has typed their own.
  useEffect(() => {
    if (titleTouched || !selectedType) return
    setTitle(`${selectedType.name} ${recordDate}`.trim())
  }, [selectedType, recordDate, titleTouched])

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

  /** Metadata for the selected type only — values for fields the type no longer
   *  defines are dropped, which matters when the type is changed during an edit. */
  const collectMetadata = () => {
    const structured: Record<string, string> = {}
    for (const f of fields) {
      const v = values[f.key]?.trim()
      if (v) structured[f.key] = v
    }
    return structured
  }

  const handleSubmit = async () => {
    // Required fields only bind once a type has actually been chosen; a record
    // may be staged untyped and classified later.
    if (selectedType) {
      for (const f of fields) {
        if (f.required && !values[f.key]?.trim()) {
          return toast.error(`${f.label} is required`)
        }
      }
    }

    setSaving(true)
    try {
      if (isEdit && record) {
        await update.mutateAsync({
          id: record.id,
          body: {
            doc_type_id: typeId || null,
            title: title.trim() || null,
            structured_metadata: collectMetadata(),
            record_date: recordDate || null,
          },
        })
        toast.success('Record updated')
      } else {
        let documentId: string | null = null
        if (file) {
          const bucket = await apiFor(domain).getBucket()
          const fd = new FormData()
          fd.append('title', title.trim() || file.name)
          fd.append('file', file)
          fd.append('bucket_id', bucket.id)
          const doc = await docvaultApi.uploadDocument(fd)
          documentId = doc.id
        }

        await create.mutateAsync({
          doc_type_id: typeId || null,
          title: title.trim() || null,
          document_id: documentId,
          structured_metadata: collectMetadata(),
          record_date: recordDate || null,
        })
        toast.success('Record created')
      }
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to ${isEdit ? 'update' : 'create'} record`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? 'Edit record' : 'New record'}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={saving}>
            {isEdit ? 'Save' : 'Create'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Title" hint="Defaults to the document type and date">
          <Input
            value={title}
            onChange={(e) => {
              setTitle(e.target.value)
              setTitleTouched(true)
            }}
            placeholder="Untitled record"
          />
        </Field>

        <Field label="Document type" hint="Optional — classify this record now or later">
          <Select value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            <option value="">— Unclassified —</option>
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

        {!isEdit && (
          <Field label="Completed document" hint="Optional — attach now, or upload to DocVault and sync later">
            <input
              type="file"
              className="mt-1 block w-full text-sm text-text-secondary file:mr-3 file:rounded-btn file:border file:border-border file:bg-bg-raised file:px-3 file:py-1.5 file:text-sm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </Field>
        )}
      </div>
    </Modal>
  )
}
