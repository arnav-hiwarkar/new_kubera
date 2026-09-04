import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, FileText, Pencil, History } from 'lucide-react'
import { cn } from '@/lib/cn'
import {
  Button,
  Field,
  Input,
  Select,
  Switch,
  StatusBadge,
  FileUploadDropzone,
  ConfirmDialog,
} from '@/components/ui'
import type { BucketResponse, DocumentResponse } from '@/api/types'
import { formatBytes, formatDate } from '@/lib/format'
import { useDocumentActions, type DocumentActions } from '../../useDocumentActions'
import { DocumentApprovalPanel } from '../../DocumentApprovalPanel'

type Tab = 'overview' | 'edit' | 'versions'
const TABS: { key: Tab; label: string; icon: typeof FileText }[] = [
  { key: 'overview', label: 'Overview', icon: FileText },
  { key: 'edit', label: 'Edit', icon: Pencil },
  { key: 'versions', label: 'Versions', icon: History },
]

export interface GraphDocumentInspectorProps {
  document: DocumentResponse | null
  buckets: BucketResponse[]
  open: boolean
  onClose: () => void
}

export function GraphDocumentInspector({
  document,
  buckets,
  open,
  onClose,
}: GraphDocumentInspectorProps) {
  const actions = useDocumentActions(document)
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => {
    setTab('overview')
  }, [document])

  if (!open || !document) return null

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
      <div
        data-testid="graph-document-inspector"
        className="absolute top-18 right-4 w-96 max-h-[calc(100vh-6rem)] overflow-hidden rounded-2xl border border-border bg-bg-surface/95 backdrop-blur-md shadow-2xl z-30 flex flex-col"
      >
        {/* Header */}
        <div className="p-4 pb-3 border-b border-border">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-2.5 min-w-0 flex-1">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
                <FileText className="w-4 h-4" />
              </span>
              <div className="min-w-0">
                <h2
                  className="text-base font-semibold text-text-primary truncate leading-snug"
                  title={document.title}
                  data-testid="inspector-document-title"
                >
                  {document.title}
                </h2>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-text-muted">
                  <StatusBadge status={document.status} />
                  <span>·</span>
                  <span className="truncate max-w-[140px]" title={bucketName}>
                    {bucketName}
                  </span>
                  <span>·</span>
                  <span className="font-mono">v{currentVersionNo}</span>
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              data-testid="inspector-close-btn"
              className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-subtle transition-colors shrink-0"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Meta row */}
          <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-text-muted">
            <span>
              Created by{' '}
              <span className="font-medium text-text-primary">
                {document.created_by_name ?? 'Unknown'}
              </span>
            </span>
            <span>·</span>
            <span>
              Updated{' '}
              <span className="font-medium text-text-primary">
                {document.updated_at ? formatDate(document.updated_at) : '—'}
              </span>
            </span>
          </div>

          {/* Tabs */}
          <div role="tablist" className="mt-3 grid grid-cols-3 gap-1 rounded-xl bg-bg-inset p-1">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                role="tab"
                type="button"
                aria-selected={tab === key}
                data-testid={`inspector-tab-${key}`}
                onClick={() => setTab(key)}
                className={cn(
                  'flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors',
                  tab === key
                    ? 'bg-bg-surface text-text-primary shadow-sm'
                    : 'text-text-muted hover:text-text-primary',
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-4">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.15 }}
            >
              {tab === 'overview' && (
                <OverviewTab document={document} currentVersion={currentVersion} actions={actions} />
              )}
              {tab === 'edit' && (
                <EditTab document={document} buckets={buckets} actions={actions} />
              )}
              {tab === 'versions' && (
                <VersionsTab
                  document={document}
                  sortedVersions={sortedVersions}
                  actions={actions}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Danger zone footer */}
        <div className="border-t border-border p-3">
          {actions.isArchived ? (
            actions.canRestore ? (
              <Button
                variant="secondary"
                onClick={actions.restore}
                loading={actions.isRestoring}
                className="w-full"
              >
                Restore document
              </Button>
            ) : (
              <p className="text-center text-xs text-text-muted">
                Only an administrator can restore an archived document.
              </p>
            )
          ) : (
            actions.canArchive && (
              <Button
                variant="danger"
                onClick={() => setConfirmArchive(true)}
                className="w-full"
              >
                Archive document
              </Button>
            )
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmArchive}
        title="Archive document?"
        message="Archiving locks the document and hides it from active lists. You can restore it later."
        confirmLabel="Archive"
        destructive
        onConfirm={doArchive}
        onCancel={() => setConfirmArchive(false)}
      />
    </>
  )
}

function OverviewTab({
  document,
  currentVersion,
  actions,
}: {
  document: DocumentResponse
  currentVersion?: DocumentResponse['versions'][number]
  actions: DocumentActions
}) {
  const facts: [string, string][] = [
    ['Created by', document.created_by_name ?? 'Unknown'],
    ['Current version by', currentVersion?.uploaded_by_name ?? 'Unknown'],
    ['Current version size', currentVersion ? formatBytes(currentVersion.size_bytes) : '—'],
    ['Versions', String(document.versions.length)],
    ['Updated', document.updated_at ? formatDate(document.updated_at) : '—'],
  ]
  return (
    <div className="flex flex-col gap-4">
      <DocumentApprovalPanel document={document} actions={actions} />
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        {facts.map(([k, v]) => (
          <div key={k} className="col-span-2 grid grid-cols-[130px_1fr] items-baseline gap-3">
            <dt className="text-xs text-text-muted">{k}</dt>
            <dd className="text-sm text-text-primary truncate" title={v}>
              {v}
            </dd>
          </div>
        ))}
      </dl>
      <div>
        <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-muted">
          Tags
        </h3>
        {document.tags.length ? (
          <div className="flex flex-wrap gap-1.5">
            {document.tags.map((t) => (
              <span
                key={t}
                className="rounded-full bg-bg-inset border border-border px-2 py-0.5 text-xs text-text-secondary"
              >
                {t}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-muted">No tags</p>
        )}
      </div>
    </div>
  )
}

function EditTab({
  document,
  buckets,
  actions,
}: {
  document: DocumentResponse
  buckets: BucketResponse[]
  actions: DocumentActions
}) {
  const isTitleUnchanged =
    !actions.titleInput.trim() || actions.titleInput.trim() === document.title

  return (
    <div className="flex flex-col gap-4">
      <DocumentApprovalPanel document={document} actions={actions} />

      {/* Status is read-only here: it moves through the workflow above, never
          by direct assignment. */}
      <Field label="Status">
        <div className="flex items-center gap-2">
          <StatusBadge status={document.status} />
          {actions.isArchived && (
            <span className="text-sm text-text-muted">Archived documents are locked.</span>
          )}
        </div>
      </Field>

      <Field
        label="Name"
        htmlFor="doc-title"
        hint={!actions.canEditMeta ? 'Locked — you cannot rename this document' : undefined}
      >
        <div className="flex gap-2">
          <Input
            id="doc-title"
            value={actions.titleInput}
            onChange={(e) => actions.setTitleInput(e.target.value)}
            disabled={!actions.canEditMeta}
            placeholder="Document name"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={actions.saveTitle}
            disabled={!actions.canEditMeta || isTitleUnchanged || actions.isMutating}
          >
            Save
          </Button>
        </div>
      </Field>

      <Field
        label="Editable"
        hint={
          actions.isPending && !actions.canReview
            ? 'Locked while pending approval. Only the assigned approver or an admin can adjust.'
            : !document.is_editable && !actions.isAdmin
              ? 'Finalized (Locked). Only an administrator can unlock this document.'
              : 'When off, the file is Final: no new versions, renaming, tags or bucket changes.'
        }
      >
        <Switch
          checked={document.is_editable}
          onChange={actions.changeEditable}
          disabled={!actions.canToggleEditable || actions.isMutating}
          label={document.is_editable ? 'Editable' : 'Locked'}
        />
      </Field>

      <Field label="Bucket" htmlFor="doc-bucket">
        <Select
          id="doc-bucket"
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

      <Field label="Tags" htmlFor="doc-tags" hint="Comma-separated">
        <div className="flex gap-2">
          <Input
            id="doc-tags"
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
    </div>
  )
}

function VersionsTab({
  document,
  sortedVersions,
  actions,
}: {
  document: DocumentResponse
  sortedVersions: DocumentResponse['versions']
  actions: DocumentActions
}) {
  return (
    <div className="flex flex-col gap-4">
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
                type="button"
                onClick={() => actions.downloadVersion(v.id, v.original_filename)}
                className="shrink-0 text-accent hover:underline text-sm font-medium"
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
        {document.status === 'archived' ? (
          <p className="text-sm text-text-muted">Archived — new versions are disabled.</p>
        ) : !actions.canUploadVersion ? (
          <p className="text-sm text-text-muted">
            This document is locked (new versions not allowed).
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
  )
}
