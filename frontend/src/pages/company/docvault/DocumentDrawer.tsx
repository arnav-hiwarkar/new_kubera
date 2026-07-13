import { useEffect, useState } from 'react'
import {
  Drawer,
  Button,
  Field,
  Input,
  Select,
  StatusBadge,
  FileUploadDropzone,
  ConfirmDialog,
  useToast,
} from '@/components/ui'
import { DOCUMENT_STATUS, humanize } from '@/api/enums'
import { ApiError } from '@/api/http'
import type { BucketResponse, DocumentResponse } from '@/api/types'
import { formatBytes, formatDate } from '@/lib/format'
import {
  useUpdateDocument,
  useArchiveDocument,
  useUploadVersion,
  useDownloadDocument,
} from '@/api/hooks/docvault'

// The dropdown offers every live status; 'archived' is reached only via the
// Archive action (which also locks the doc), never as a plain status pick.
const LIVE_STATUSES = DOCUMENT_STATUS.filter((s) => s !== 'archived')

export interface DocumentDrawerProps {
  document: DocumentResponse | null
  open: boolean
  onClose: () => void
  buckets: BucketResponse[]
}

export function DocumentDrawer({ document, open, onClose, buckets }: DocumentDrawerProps) {
  const toast = useToast()
  const update = useUpdateDocument()
  const archive = useArchiveDocument()
  const uploadVersion = useUploadVersion()
  const download = useDownloadDocument()

  const [tagsInput, setTagsInput] = useState('')
  const [confirmArchive, setConfirmArchive] = useState(false)

  useEffect(() => {
    setTagsInput(document?.tags.join(', ') ?? '')
  }, [document])

  if (!document) return null

  const isArchived = document.status === 'archived'
  const bucketName = buckets.find((b) => b.id === document.bucket_id)?.name ?? 'Uncategorized'
  const currentVersionNo =
    document.versions.find((v) => v.id === document.current_version_id)?.version_number ??
    Math.max(0, ...document.versions.map((v) => v.version_number))
  const sortedVersions = [...document.versions].sort((a, b) => b.version_number - a.version_number)

  const wrap = async (p: Promise<unknown>, ok: string) => {
    try {
      await p
      toast.success(ok)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Action failed')
    }
  }

  const changeStatus = (status: string) =>
    wrap(update.mutateAsync({ id: document.id, body: { status: status as never } }), 'Status updated')

  const changeBucket = (value: string) =>
    wrap(
      update.mutateAsync({ id: document.id, body: { bucket_id: (value || null) as never } }),
      'Moved',
    )

  const saveTags = () => {
    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)
    return wrap(update.mutateAsync({ id: document.id, body: { tags } }), 'Tags saved')
  }

  const restore = () =>
    wrap(
      update.mutateAsync({ id: document.id, body: { status: 'uploaded' as never, is_editable: true } }),
      'Document restored',
    )

  const doArchive = async () => {
    await wrap(archive.mutateAsync(document.id), 'Document archived')
    setConfirmArchive(false)
  }

  const handleNewVersion = (files: File[]) => {
    const fd = new FormData()
    fd.append('file', files[0])
    void wrap(uploadVersion.mutateAsync({ id: document.id, formData: fd }), 'New version uploaded')
  }

  const downloadVersion = (versionId: string, filename: string) =>
    void wrap(download.mutateAsync({ id: document.id, versionId, filename }), 'Download started')

  return (
    <>
      <Drawer
        open={open}
        onClose={onClose}
        title={document.title}
        subtitle={
          <span className="flex items-center gap-2">
            <StatusBadge status={document.status} />
            <span className="text-text-muted">·</span>
            <span>{bucketName}</span>
            <span className="text-text-muted">·</span>
            <span className="font-mono">v{currentVersionNo}</span>
          </span>
        }
        footer={
          isArchived ? (
            <Button variant="secondary" onClick={restore} loading={update.isPending}>
              Restore document
            </Button>
          ) : (
            <Button variant="danger" onClick={() => setConfirmArchive(true)}>
              Archive
            </Button>
          )
        }
      >
        <div className="flex flex-col gap-5">
          {/* Status */}
          <Field label="Status">
            {isArchived ? (
              <div className="flex items-center gap-2">
                <StatusBadge status="archived" />
                <span className="text-sm text-text-muted">Archived documents are locked.</span>
              </div>
            ) : (
              <Select
                value={document.status}
                onChange={(e) => changeStatus(e.target.value)}
                disabled={update.isPending}
              >
                {LIVE_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {humanize(s)}
                  </option>
                ))}
              </Select>
            )}
          </Field>

          {/* Bucket */}
          <Field label="Bucket">
            <Select
              value={document.bucket_id ?? ''}
              onChange={(e) => changeBucket(e.target.value)}
              disabled={update.isPending || isArchived}
            >
              <option value="">Uncategorized</option>
              {buckets.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          </Field>

          {/* Tags */}
          <Field label="Tags" hint="Comma-separated">
            <div className="flex gap-2">
              <Input
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
                placeholder="board, 2026"
                disabled={isArchived}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={saveTags}
                disabled={isArchived || update.isPending}
              >
                Save
              </Button>
            </div>
          </Field>

          {/* Version history */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
              Version history
            </h3>
            <ul className="flex flex-col divide-y divide-border rounded-card border border-border">
              {sortedVersions.map((v) => (
                <li key={v.id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-medium text-text-primary">
                      v{v.version_number}
                    </span>
                    {v.id === document.current_version_id && (
                      <span className="rounded-full bg-accent-subtle px-1.5 py-0.5 text-xs text-accent">
                        current
                      </span>
                    )}
                    <span className="text-text-muted">
                      {formatBytes(v.size_bytes)} · {formatDate(v.uploaded_at)}
                    </span>
                  </div>
                  <button
                    onClick={() => downloadVersion(v.id, v.original_filename)}
                    className="text-accent hover:underline"
                  >
                    Download
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {/* Upload new version */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
              Upload new version
            </h3>
            {isArchived ? (
              <p className="text-sm text-text-muted">Archived — new versions are disabled.</p>
            ) : !document.is_editable ? (
              <p className="text-sm text-text-muted">
                This document is locked (new versions not allowed).
              </p>
            ) : (
              <FileUploadDropzone
                onFilesSelected={handleNewVersion}
                disabled={uploadVersion.isPending}
                hint={uploadVersion.isPending ? 'Uploading…' : 'Replaces the current version'}
              />
            )}
          </div>
        </div>
      </Drawer>

      <ConfirmDialog
        open={confirmArchive}
        title="Archive document?"
        message="Archiving locks the document and hides it from active lists. You can restore it later."
        confirmLabel="Archive"
        destructive
        loading={archive.isPending}
        onConfirm={doArchive}
        onCancel={() => setConfirmArchive(false)}
      />
    </>
  )
}
