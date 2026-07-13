import { useEffect, useState } from 'react'
import { Modal, Button, Field, Input, Select, Textarea, useToast } from '@/components/ui'
import { docvaultApi } from '@/api/endpoints/docvault'
import { useCreateDocumentType, useUpdateDocumentType, type Domain } from '@/api/hooks/compliance'
import type { DocumentTypeResponse } from '@/api/types'
import { resolveBucket } from './buckets'
import { readFields, slugify, type FieldDef, type FieldType, FIELD_TYPES } from './schema'

/** Editable row in the builder — options kept as raw text for the textarea. */
interface Row {
  label: string
  type: FieldType
  optionsText: string
  required: boolean
}

function toRow(f: FieldDef): Row {
  return {
    label: f.label,
    type: f.type,
    optionsText: (f.options ?? []).join('\n'),
    required: !!f.required,
  }
}

interface DocumentTypeModalProps {
  open: boolean
  onClose: () => void
  domain: Domain
  /** null → create; otherwise edit a company-owned type. */
  docType: DocumentTypeResponse | null
}

export function DocumentTypeModal({ open, onClose, domain, docType }: DocumentTypeModalProps) {
  const toast = useToast()
  const create = useCreateDocumentType(domain)
  const update = useUpdateDocumentType(domain)

  const [name, setName] = useState('')
  const [dueRule, setDueRule] = useState('')
  const [rows, setRows] = useState<Row[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setName(docType?.name ?? '')
    setDueRule(docType?.due_date_rule ?? '')
    setRows(readFields(docType?.metadata_schema).map(toRow))
    setFile(null)
    setSaving(false)
  }, [open, docType])

  const addRow = () =>
    setRows((r) => [...r, { label: '', type: 'text', optionsText: '', required: false }])
  const removeRow = (i: number) => setRows((r) => r.filter((_, idx) => idx !== i))
  const updateRow = (i: number, patch: Partial<Row>) =>
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)))

  const buildFields = (): FieldDef[] =>
    rows
      .filter((r) => r.label.trim())
      .map((r) => {
        const options = r.optionsText
          .split(/[\n,]/)
          .map((o) => o.trim())
          .filter(Boolean)
        return {
          key: slugify(r.label),
          label: r.label.trim(),
          type: r.type,
          ...(r.type === 'dropdown' ? { options } : {}),
          ...(r.required ? { required: true } : {}),
        }
      })

  const handleSubmit = async () => {
    if (!name.trim()) return toast.error('Name is required')
    setSaving(true)
    try {
      let templateFileId = docType?.template_file_id ?? null
      if (file) {
        const bucketId = await resolveBucket('Compliance Templates')
        const fd = new FormData()
        fd.append('title', `${name.trim()} template`)
        fd.append('file', file)
        fd.append('bucket_id', bucketId)
        const doc = await docvaultApi.uploadDocument(fd)
        templateFileId = doc.id
      }

      const body = {
        name: name.trim(),
        template_file_id: templateFileId,
        metadata_schema: { fields: buildFields() },
        due_date_rule: dueRule.trim() || null,
      }

      if (docType) {
        await update.mutateAsync({ id: docType.id, body })
        toast.success('Document type updated')
      } else {
        await create.mutateAsync(body)
        toast.success('Document type created')
      }
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save document type')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={docType ? 'Edit document type' : 'New document type'}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={saving}>
            {docType ? 'Save' : 'Create'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Name" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Board Meeting Minutes" />
        </Field>

        <Field label="Template file" hint={docType?.template_file_id ? 'A template is attached — upload to replace it.' : 'Optional — a fillable template members download.'}>
          <input
            type="file"
            className="mt-1 block w-full text-sm text-text-secondary file:mr-3 file:rounded-btn file:border file:border-border file:bg-bg-raised file:px-3 file:py-1.5 file:text-sm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Field>

        <Field label="Due date rule" hint="Optional free text, e.g. 'Within 30 days of AGM'">
          <Input value={dueRule} onChange={(e) => setDueRule(e.target.value)} />
        </Field>

        <div className="rounded-card border border-border p-3">
          <div className="mb-3 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-text-primary">Fields</h4>
            <Button variant="secondary" onClick={addRow}>
              Add field
            </Button>
          </div>
          {rows.length === 0 ? (
            <p className="text-sm text-text-muted">No fields yet. Add fields to capture per-record data.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {rows.map((row, i) => (
                <div key={i} className="rounded-card border border-border p-3">
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Label">
                      <Input
                        value={row.label}
                        onChange={(e) => updateRow(i, { label: e.target.value })}
                        placeholder="e.g. Meeting date"
                      />
                    </Field>
                    <Field label="Type">
                      <Select
                        value={row.type}
                        onChange={(e) => updateRow(i, { type: e.target.value as FieldType })}
                      >
                        {FIELD_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t.charAt(0).toUpperCase() + t.slice(1)}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                  {row.type === 'dropdown' && (
                    <Field label="Options" hint="One per line or comma-separated" className="mt-3">
                      <Textarea
                        value={row.optionsText}
                        onChange={(e) => updateRow(i, { optionsText: e.target.value })}
                        rows={3}
                        placeholder={'Option A\nOption B'}
                      />
                    </Field>
                  )}
                  <div className="mt-3 flex items-center justify-between">
                    <label className="flex items-center gap-2 text-sm text-text-secondary">
                      <input
                        type="checkbox"
                        checked={row.required}
                        onChange={(e) => updateRow(i, { required: e.target.checked })}
                      />
                      Required
                    </label>
                    <Button variant="ghost" onClick={() => removeRow(i)}>
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
