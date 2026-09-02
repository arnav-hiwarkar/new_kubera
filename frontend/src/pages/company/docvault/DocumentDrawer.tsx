import { useEffect, useState } from 'react'
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
  useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import type { BucketResponse, DocumentResponse } from '@/api/types'
import { formatBytes, formatDate } from '@/lib/format'
import { cn } from '@/lib/cn'
import {
  useUpdateDocument,
  useReviewDocument,
  useRequestApproval,
  useArchiveDocument,
  useRestoreDocument,
  useUploadVersion,
  useDownloadDocument,
} from '@/api/hooks/docvault'
import { useCompanyAuth } from '@/auth/company'
import { CheckCircle2, AlertTriangle, Clock, MessageSquareQuote } from 'lucide-react'
import { ApproverPicker } from './ApproverPicker'

export interface DocumentDrawerProps {
  document: DocumentResponse | null
  open: boolean
  onClose: () => void
  buckets: BucketResponse[]
}

export function DocumentDrawer({ document, open, onClose, buckets }: DocumentDrawerProps) {
  const toast = useToast()
  const { profile } = useCompanyAuth()
  const update = useUpdateDocument()
  const review = useReviewDocument()
  const requestApproval = useRequestApproval()
  const archive = useArchiveDocument()
  const restoreMutation = useRestoreDocument()
  const uploadVersion = useUploadVersion()
  const download = useDownloadDocument()

  const [tagsInput, setTagsInput] = useState('')
  const [titleInput, setTitleInput] = useState('')
  const [approvalNotesInput, setApprovalNotesInput] = useState('')
  const [reapproverId, setReapproverId] = useState<string | null>(null)
  const [confirmArchive, setConfirmArchive] = useState(false)

  useEffect(() => {
    setTagsInput(document?.tags.join(', ') ?? '')
    setTitleInput(document?.title ?? '')
    setApprovalNotesInput(document?.approval_notes ?? '')
    setReapproverId(document?.approver_id ?? null)
  }, [document])

  if (!document) return null

  const isArchived = document.status === 'archived'
  const isPendingApproval = document.status === 'pending_approval'
  const isApprover = profile?.id === document.approver_id
  const isAdmin = profile?.role === 'admin'
  const isCreator = profile?.id === document.created_by
  const isCreatorOrAdmin = isCreator || isAdmin
  const canReview = isPendingApproval && (isApprover || isAdmin)
  const canRequestApproval =
    (document.status === 'uploaded' || document.status === 'action_required') &&
    isCreatorOrAdmin &&
    !isArchived

  // A locked (non-editable) document freezes its name, tags, bucket and new
  // versions. Status changes (incl. archive) and the editable toggle stay open.
  const locked = !document.is_editable
  const editFrozen = locked || (isPendingApproval && !canReview)

  const bucketName = buckets.find((b) => b.id === document.bucket_id)?.name ?? 'Uncategorized'
  const currentVersion = document.versions.find((v) => v.id === document.current_version_id)
  const currentVersionNo =
    currentVersion?.version_number ??
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

  const handleApprove = () =>
    wrap(
      review.mutateAsync({
        id: document.id,
        body: { decision: 'verified', approval_notes: approvalNotesInput.trim() || undefined },
      }),
      'Document approved (Status: Verified)',
    )

  const handleRequestChanges = () => {
    if (!approvalNotesInput.trim()) {
      toast.error('Please enter notes explaining the requested changes')
      return
    }
    return wrap(
      review.mutateAsync({
        id: document.id,
        body: { decision: 'action_required', approval_notes: approvalNotesInput.trim() },
      }),
      'Document flagged for changes (Status: Action Required)',
    )
  }

  const handleRequestApproval = () => {
    const target = reapproverId || document.approver_id
    if (!target) {
      toast.error('Please select an approver')
      return
    }
    return wrap(
      requestApproval.mutateAsync({
        id: document.id,
        body: { approver_id: target },
      }),
      document.status === 'action_required'
        ? 'Document resubmitted for approval'
        : 'Document submitted for approval',
    )
  }

  const changeBucket = (value: string) =>
    wrap(
      update.mutateAsync({ id: document.id, body: { bucket_id: (value || null) as never } }),
      'Moved',
    )

  const saveTitle = () => {
    const title = titleInput.trim()
    if (!title || title === document.title) return
    return wrap(update.mutateAsync({ id: document.id, body: { title } }), 'Name updated')
  }

  const changeEditable = (checked: boolean) =>
    wrap(update.mutateAsync({ id: document.id, body: { is_editable: checked } }), 'Updated')

  const saveTags = () => {
    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)
    return wrap(update.mutateAsync({ id: document.id, body: { tags } }), 'Tags saved')
  }

  const restore = () =>
    wrap(
      restoreMutation.mutateAsync(document.id),
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
          isArchived ? (
            <Button
              variant="secondary"
              onClick={restore}
              loading={restoreMutation.isPending}
              disabled={!isAdmin}
              title={!isAdmin ? 'Only administrators can restore archived documents' : undefined}
            >
              Restore document
            </Button>
          ) : (
            <Button
              variant="danger"
              onClick={() => setConfirmArchive(true)}
              disabled={isPendingApproval && !canReview}
              title={isPendingApproval && !canReview ? 'Cannot archive while pending approval' : undefined}
            >
              Archive
            </Button>
          )
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

          {/* Pending Approval Review Section */}
          {isPendingApproval && (
            <div className="rounded-card border border-amber-500/30 bg-amber-500/5 p-4 flex flex-col gap-3">
              <div className="flex items-start gap-2.5">
                <Clock className="h-5 w-5 shrink-0 text-amber-400 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-semibold text-text-primary">
                    {canReview ? 'Review & Approval Required' : 'Awaiting Document Approval'}
                  </h4>
                  <p className="text-xs text-text-muted mt-0.5">
                    {canReview
                      ? `Requested by ${document.created_by_name || 'team member'} ${
                          document.approval_requested_at ? `on ${formatDate(document.approval_requested_at)}` : ''
                        }`
                      : `Assigned to ${document.approver_name || 'the designated approver'}. Edits are paused until review is completed.`}
                  </p>
                </div>
              </div>

              {canReview && (
                <div className="flex flex-col gap-3 pt-2 border-t border-amber-500/20">
                  <Field label="Review notes / feedback" htmlFor="approval-notes" hint="Optional for approval; required when requesting changes">
                    <Input
                      id="approval-notes"
                      value={approvalNotesInput}
                      onChange={(e) => setApprovalNotesInput(e.target.value)}
                      placeholder="e.g. Verified compliance checklist, ready for submission"
                      disabled={update.isPending}
                    />
                  </Field>

                  <div className="flex flex-wrap items-center gap-2.5 pt-1">
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleApprove}
                      loading={review.isPending}
                      className="bg-emerald-600 hover:bg-emerald-500 text-white"
                    >
                      <CheckCircle2 className="h-4 w-4 mr-1.5" />
                      Approve (Verified)
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleRequestChanges}
                      loading={review.isPending}
                      className="border-amber-500/40 text-amber-400 hover:bg-amber-500/10"
                    >
                      <AlertTriangle className="h-4 w-4 mr-1.5" />
                      Request Changes
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Review Note / Change Request display */}
          {!isPendingApproval && document.approval_notes && (
            <div
              className={cn(
                'rounded-card border p-3 flex items-start gap-2.5',
                document.status === 'action_required'
                  ? 'border-amber-500/40 bg-amber-500/10'
                  : 'border-border bg-bg-surface',
              )}
            >
              <MessageSquareQuote
                className={cn(
                  'h-4 w-4 shrink-0 mt-0.5',
                  document.status === 'action_required' ? 'text-amber-400' : 'text-accent',
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                    {document.status === 'action_required' ? 'Requested Changes Note' : 'Review Note'} ·{' '}
                    {document.approver_name || 'Approver'}
                  </span>
                  {document.approved_at && (
                    <span className="text-xs text-text-muted">{formatDate(document.approved_at)}</span>
                  )}
                </div>
                <p className="text-sm text-text-primary mt-1">{document.approval_notes}</p>
              </div>
            </div>
          )}

          {/* Submit / Resubmit for Approval card */}
          {canRequestApproval && (
            <div className="rounded-card border border-accent/30 bg-accent/5 p-4 flex flex-col gap-3">
              <div className="flex items-start gap-2.5">
                <Clock className="h-5 w-5 shrink-0 text-accent mt-0.5" />
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-semibold text-text-primary">
                    {document.status === 'action_required' ? 'Resubmit for Review' : 'Submit for Review'}
                  </h4>
                  <p className="text-xs text-text-muted mt-0.5">
                    {document.status === 'action_required'
                      ? 'Once revisions are complete, resubmit this document for approval.'
                      : 'Request an approver to review and verify this document.'}
                  </p>
                </div>
              </div>

              <div className="flex flex-col gap-2 pt-2 border-t border-accent/20">
                <Field label="Assign Approver">
                  <ApproverPicker
                    value={reapproverId}
                    onChange={setReapproverId}
                    bucketId={document.bucket_id}
                    disabled={requestApproval.isPending}
                  />
                </Field>
                <div className="flex justify-end pt-1">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleRequestApproval}
                    loading={requestApproval.isPending}
                    disabled={!reapproverId && !document.approver_id}
                  >
                    {document.status === 'action_required' ? 'Resubmit for Approval' : 'Submit for Approval'}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* Name */}
          <Field label="Name" hint={editFrozen ? 'Locked from renaming' : undefined}>
            <div className="flex gap-2">
              <Input
                value={titleInput}
                onChange={(e) => setTitleInput(e.target.value)}
                disabled={isArchived || editFrozen}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={saveTitle}
                disabled={isArchived || editFrozen || update.isPending}
              >
                Save
              </Button>
            </div>
          </Field>

          {/* Editable toggle */}
          <Field
            label="Editable"
            hint={
              isPendingApproval && !canReview
                ? 'Locked while pending approval. Only the assigned approver or admin can adjust.'
                : !document.is_editable && !isAdmin
                ? 'Finalized (Locked). Only an administrator can unlock this document.'
                : 'When off, the file is Final: no new versions, renaming, tags or bucket changes.'
            }
          >
            <Switch
              checked={document.is_editable}
              onChange={changeEditable}
              disabled={isArchived || update.isPending || (isPendingApproval && !canReview) || (!document.is_editable && !isAdmin)}
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
          <Field label="Bucket">
            <Select
              value={document.bucket_id ?? ''}
              onChange={(e) => changeBucket(e.target.value)}
              disabled={update.isPending || isArchived || editFrozen}
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
                disabled={isArchived || editFrozen}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={saveTags}
                disabled={isArchived || editFrozen || update.isPending}
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
                    onClick={() => downloadVersion(v.id, v.original_filename)}
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
            {isArchived ? (
              <p className="text-sm text-text-muted">Archived — new versions are disabled.</p>
            ) : !document.is_editable ? (
              <p className="text-sm text-text-muted">
                This document is marked as Final (new versions disabled).
              </p>
            ) : isPendingApproval && !canReview ? (
              <p className="text-sm text-text-muted">
                Document is pending approval by {document.approver_name || 'approver'}.
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
