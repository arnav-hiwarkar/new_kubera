import { useState } from 'react'
import { Modal, Button, Field, Input, Select, FileUploadDropzone, useToast } from '@/components/ui'
import { useUploadDocument } from '@/api/hooks/docvault'
import { ApiError } from '@/api/http'
import type { BucketResponse } from '@/api/types'
import { ApproverPicker } from './ApproverPicker'

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
  const [needsApproval, setNeedsApproval] = useState(false)
  const [approverId, setApproverId] = useState<string | null>(null)
  const [titleTouched, setTitleTouched] = useState(false)

  const reset = () => {
    setFile(null)
    setTitle('')
    setBucketId(defaultBucketId ?? '')
    setTags('')
    setIsEditable(true)
    setNeedsApproval(false)
    setApproverId(null)
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

  const canSubmit =
    !!file &&
    title.trim().length > 0 &&
    (!needsApproval || !!approverId) &&
    !upload.isPending

  const handleSubmit = async () => {
    if (!file || !title.trim()) return
    if (needsApproval && !approverId) {
      toast.error('Please select an approver')
      return
    }

    const fd = new FormData()
    fd.append('title', title.trim())
    fd.append('file', file)
    if (bucketId) fd.append('bucket_id', bucketId)
    if (tags.trim()) fd.append('tags', tags.trim())
    fd.append('is_editable', String(isEditable))
    fd.append('needs_approval', String(needsApproval))
    if (needsApproval && approverId) {
      fd.append('approver_id', approverId)
    }

    try {
      await upload.mutateAsync(fd)
      toast.success(needsApproval ? 'Document uploaded & sent for approval' : 'Document uploaded')
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
            {needsApproval ? 'Upload & Request Approval' : 'Upload'}
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

        {/* Approval request section */}
        <div className="rounded-lg border border-border bg-bg-surface/50 p-3 flex flex-col gap-3">
          <label className="flex cursor-pointer items-center justify-between text-sm font-medium text-text-primary">
            <span className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={needsApproval}
                onChange={(e) => {
                  setNeedsApproval(e.target.checked)
                  if (!e.target.checked) setApproverId(null)
                }}
                className="h-4 w-4 accent-accent rounded"
              />
              <span>Request document approval</span>
            </span>
            <span className="text-xs text-text-muted">Sends notification to reviewer</span>
          </label>

          {needsApproval && (
            <Field label="Designated Approver" required hint="Only users with DocVault access are eligible">
              <ApproverPicker
                value={approverId}
                onChange={setApproverId}
                bucketId={bucketId || null}
                buckets={buckets}
              />
            </Field>
          )}
        </div>

        {/* Editable / Final toggle */}
        <label className="flex cursor-pointer items-start gap-2.5 text-sm text-text-secondary">
          <input
            type="checkbox"
            checked={!isEditable}
            onChange={(e) => setIsEditable(!e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-accent rounded"
          />
          <div>
            <span className="font-medium text-text-primary">Mark as Final (Lock document)</span>
            <p className="text-xs text-text-muted">
              When locked, further edits, renaming, and new version uploads will be disabled.
            </p>
          </div>
        </label>
      </div>
    </Modal>
  )
}
