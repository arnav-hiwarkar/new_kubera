import { useState } from 'react'
import { Modal, Button, Field, Input, Select, FileUploadDropzone, useToast } from '@/components/ui'
import { useUploadDocument } from '@/api/hooks/docvault'
import { ApiError } from '@/api/http'
import type { BucketResponse } from '@/api/types'

export interface UploadDocumentModalProps {
  open: boolean
  onClose: () => void
  buckets: BucketResponse[]
  /** Preselect a bucket (e.g. the one currently filtered in the rail). */
  defaultBucketId?: string
}

function stripExtension(filename: string) {
  const dot = filename.lastIndexOf('.')
  return dot > 0 ? filename.slice(0, dot) : filename
}

export function UploadDocumentModal({
  open,
  onClose,
  buckets,
  defaultBucketId,
}: UploadDocumentModalProps) {
  const toast = useToast()
  const upload = useUploadDocument()

  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [bucketId, setBucketId] = useState(defaultBucketId ?? '')
  const [tags, setTags] = useState('')
  const [isEditable, setIsEditable] = useState(true)
  const [titleTouched, setTitleTouched] = useState(false)

  const reset = () => {
    setFile(null)
    setTitle('')
    setBucketId(defaultBucketId ?? '')
    setTags('')
    setIsEditable(true)
    setTitleTouched(false)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleFile = (files: File[]) => {
    const f = files[0]
    setFile(f)
    // Prefill the title from the filename unless the user already typed one.
    if (!titleTouched && !title) setTitle(stripExtension(f.name))
  }

  const canSubmit = !!file && title.trim().length > 0 && !upload.isPending

  const handleSubmit = async () => {
    if (!file || !title.trim()) return
    const fd = new FormData()
    fd.append('title', title.trim())
    fd.append('file', file)
    if (bucketId) fd.append('bucket_id', bucketId)
    if (tags.trim()) fd.append('tags', tags.trim())
    fd.append('is_editable', String(isEditable))
    try {
      await upload.mutateAsync(fd)
      toast.success('Document uploaded')
      handleClose()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Upload failed')
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Upload document"
      footer={
        <>
          <Button variant="secondary" onClick={handleClose} disabled={upload.isPending}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={upload.isPending} disabled={!canSubmit}>
            Upload
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <FileUploadDropzone
          onFilesSelected={handleFile}
          hint={file ? `Selected: ${file.name} (${(file.size / 1024).toFixed(0)} KB)` : 'Any file type'}
        />
        <Field label="Title" htmlFor="doc-title" required>
          <Input
            id="doc-title"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value)
              setTitleTouched(true)
            }}
            placeholder="e.g. Q3 Board Minutes"
          />
        </Field>
        <Field label="Bucket" htmlFor="doc-bucket" hint="Optional — leave blank for Uncategorized">
          <Select id="doc-bucket" value={bucketId} onChange={(e) => setBucketId(e.target.value)}>
            <option value="">Uncategorized</option>
            {buckets.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Tags" htmlFor="doc-tags" hint="Comma-separated">
          <Input
            id="doc-tags"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="board, 2026, finance"
          />
        </Field>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={isEditable}
            onChange={(e) => setIsEditable(e.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          Allow new versions to be uploaded later
        </label>
      </div>
    </Modal>
  )
}
