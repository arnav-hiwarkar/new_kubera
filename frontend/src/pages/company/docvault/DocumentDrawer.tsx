import { useState } from 'react'
import {
  Drawer,
  Button,
  Field,
  Input,
  Select,
  Switch,
  StatusBadge,
  FinalBadge,
  FileUploadDropzone,
  ConfirmDialog,
} from '@/components/ui'
import type { BucketResponse, DocumentResponse } from '@/api/types'
import { formatBytes, formatDate } from '@/lib/format'
import { useDocumentActions } from './useDocumentActions'
import { DocumentApprovalPanel } from './DocumentApprovalPanel'

export interface DocumentDrawerProps {
  document: DocumentResponse | null
  open: boolean
  onClose: () => void
  buckets: BucketResponse[]
}

export function DocumentDrawer({ document, open, onClose, buckets }: DocumentDrawerProps) {
  const actions = useDocumentActions(document)
  const [confirmArchive, setConfirmArchive] = useState(false)

  if (!document) return null

  const bucketName = buckets.find((b) => b.id === document.bucket_id)?.name ?? 'Uncategorized'
  const currentVersion = document.versions.find((v) => v.id === document.current_version_id)
  const currentVersionNo =
    currentVersion?.version_number ??
    Math.max(0, ...document.versions.map((v) => v.version_number))
  const sortedVersions = [...document.versions].sort((a, b) => b.version_number - a.version_number)

  const doArchive = async () => {
    await actions.doArchive()
    setConfirmArchive(false)
  }

  return (
    <>
      <Drawer
        open={open}
        onClose={onClose}
        title={document.title}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={document.status} />
            {!document.is_editable && <FinalBadge />}
            <span className="text-text-muted">·</span>
            <span>{bucketName}</span>
            <span className="text-text-muted">·</span>
            <span className="font-mono">v{currentVersionNo}</span>
          </span>
        }
        footer={
          actions.isArchived ? (
            actions.canRestore ? (
              <Button
                variant="secondary"
                onClick={actions.restore}
                loading={actions.isRestoring}
              >
                Restore document
              </Button>
            ) : (
              <p className="text-center text-xs text-text-muted">
                Only an administrator can restore an archived document.
              </p>
            )
          ) : actions.canArchive ? (
            <Button
              variant="danger"
              onClick={() => setConfirmArchive(true)}
            >
              Archive
            </Button>
          ) : null
        }
      >
        <div className="flex flex-col gap-5">
          {/* Uploader meta */}
          <div className="flex flex-wrap gap-x-2 gap-y-1 text-sm text-text-secondary">
            <span className="inline-flex min-w-0 max-w-full items-center gap-1">
              <span className="shrink-0 text-text-muted">Created by</span>
              <span className="truncate font-medium text-text-primary" title={document.created_by_name ?? 'Unknown'}>
                {document.created_by_name ?? 'Unknown'}
              </span>
            </span>
            <span className="shrink-0 text-text-muted">·</span>
            <span className="inline-flex min-w-0 max-w-full items-center gap-1">
              <span className="shrink-0 text-text-muted">Current version by</span>
              <span
                className="truncate font-medium text-text-primary"
                title={currentVersion?.uploaded_by_name ?? 'Unknown'}
              >
                {currentVersion?.uploaded_by_name ?? 'Unknown'}
              </span>
            </span>
          </div>

          <DocumentApprovalPanel document={document} actions={actions} />

          {/* Name */}
          <Field label="Name" htmlFor="drawer-title" hint={!actions.canEditMeta ? 'Locked from renaming' : undefined}>
            <div className="flex gap-2">
              <Input
                id="drawer-title"
                value={actions.titleInput}
                onChange={(e) => actions.setTitleInput(e.target.value)}
                disabled={!actions.canEditMeta}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={actions.saveTitle}
                disabled={!actions.canEditMeta || actions.titleInput.trim() === document.title || !actions.titleInput.trim() || actions.isMutating}
              >
                Save
              </Button>
            </div>
          </Field>

          {/* Editable toggle */}
          <Field
            label="Editable"
            hint={
              actions.isPending && !actions.canReview
                ? 'Locked while pending approval. Only the assigned approver or admin can adjust.'
                : !document.is_editable && !actions.isAdmin
                ? 'Finalized (Locked). Only an administrator can unlock this document.'
                : 'When off, the file is Final: no new versions, renaming, tags or bucket changes.'
            }
          >
            <Switch
              checked={document.is_editable}
              onChange={actions.changeEditable}
              disabled={!actions.canToggleEditable || actions.isMutating}
              label={document.is_editable ? 'Editable' : 'Final (Locked)'}
            />
          </Field>

          {/* Status */}
          <Field label="Status">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <StatusBadge status={document.status} />
                {document.status === 'verified' && (
                  <span className="text-xs text-text-muted">
                    {document.approved_by_name ? `Approved by ${document.approved_by_name}` : 'Approved'}
                    {document.approved_at ? ` on ${formatDate(document.approved_at)}` : ''}
                  </span>
                )}
                {document.status === 'pending_approval' && (
                  <span className="text-xs text-text-muted">
                    Awaiting review by {document.approver_name || 'assigned approver'}
                  </span>
                )}
                {document.status === 'action_required' && (
                  <span className="text-xs text-amber-400">
                    Changes requested by approver
                  </span>
                )}
                {document.status === 'archived' && (
                  <span className="text-xs text-text-muted">Archived documents are locked</span>
                )}
              </div>
            </div>
          </Field>

          {/* Bucket */}
          <Field label="Bucket" htmlFor="drawer-bucket">
            <Select
              id="drawer-bucket"
              value={document.bucket_id ?? ''}
              onChange={(e) => actions.changeBucket(e.target.value)}
              disabled={!actions.canEditMeta || actions.isMutating}
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
          <Field label="Tags" htmlFor="drawer-tags" hint="Comma-separated">
            <div className="flex gap-2">
              <Input
                id="drawer-tags"
                value={actions.tagsInput}
                onChange={(e) => actions.setTagsInput(e.target.value)}
                placeholder="board, 2026"
                disabled={!actions.canEditMeta}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={actions.saveTags}
                disabled={!actions.canEditMeta || actions.isMutating}
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
                <li key={v.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-medium text-text-primary">
                        v{v.version_number}
                      </span>
                      {v.id === document.current_version_id && (
                        <span className="rounded-full bg-accent-subtle px-1.5 py-0.5 text-xs text-accent">
                          current
                        </span>
                      )}
                    </div>
                    <span className="truncate text-text-muted" title={v.uploaded_by_name ?? 'Unknown'}>
                      {formatBytes(v.size_bytes)} · {formatDate(v.uploaded_at)} · by{' '}
                      {v.uploaded_by_name ?? 'Unknown'}
                    </span>
                  </div>
                  <button
                    onClick={() => actions.downloadVersion(v.id, v.original_filename)}
                    className="shrink-0 text-accent hover:underline"
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
            {actions.isArchived ? (
              <p className="text-sm text-text-muted">Archived — new versions are disabled.</p>
            ) : !document.is_editable ? (
              <p className="text-sm text-text-muted">
                This document is marked as Final (new versions disabled).
              </p>
            ) : actions.isPending && !actions.canReview ? (
              <p className="text-sm text-text-muted">
                Document is pending approval by {document.approver_name || 'approver'}.
              </p>
            ) : !actions.canUploadVersion ? (
              <p className="text-sm text-text-muted">
                You do not have permission to upload new versions.
              </p>
            ) : (
              <FileUploadDropzone
                onFilesSelected={actions.handleNewVersion}
                disabled={actions.isUploadingVersion}
                hint={actions.isUploadingVersion ? 'Uploading…' : 'Replaces the current version'}
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
        loading={actions.isMutating}
        onConfirm={doArchive}
        onCancel={() => setConfirmArchive(false)}
      />
    </>
  )
}
