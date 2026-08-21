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
  const toast = useToast()
  const update = useUpdateDocument()
  const archive = useArchiveDocument()
  const uploadVersion = useUploadVersion()
  const download = useDownloadDocument()

  const [tagsInput, setTagsInput] = useState('')
  const [titleInput, setTitleInput] = useState('')
  const [confirmArchive, setConfirmArchive] = useState(false)
  const [tab, setTab] = useState<Tab>('overview')

  useEffect(() => {
    setTagsInput(document?.tags.join(', ') ?? '')
    setTitleInput(document?.title ?? '')
    setTab('overview')
  }, [document])

  if (!open || !document) return null

  const isArchived = document.status === 'archived'
  // A locked (non-editable) document freezes its name, tags, bucket and new
  // versions. Status changes (incl. archive) and the editable toggle stay open.
  const locked = !document.is_editable
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

  const changeStatus = (status: string) =>
    wrap(update.mutateAsync({ id: document.id, body: { status: status as never } }), 'Status updated')

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
      update.mutateAsync({ id: document.id, body: { status: 'uploaded' as never, is_editable: true } }),
      'Document restored',
    )

  const doArchive = async () => {
    await wrap(archive.mutateAsync(document.id), 'Document archived')
    setConfirmArchive(false)
  }

  const handleNewVersion = (files: File[]) => {
    if (!files.length) return
    const fd = new FormData()
    fd.append('file', files[0])
    void wrap(uploadVersion.mutateAsync({ id: document.id, formData: fd }), 'New version uploaded')
  }

  const downloadVersion = (versionId: string, filename: string) =>
    void wrap(download.mutateAsync({ id: document.id, versionId, filename }), 'Download started')

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
              {tab === 'overview' && <OverviewTab document={document} currentVersion={currentVersion} />}
              {tab === 'edit' && (
                <EditTab
                  document={document}
                  buckets={buckets}
                  locked={locked}
                  isArchived={isArchived}
                  titleInput={titleInput}
                  setTitleInput={setTitleInput}
                  tagsInput={tagsInput}
                  setTagsInput={setTagsInput}
                  saveTitle={saveTitle}
                  saveTags={saveTags}
                  changeEditable={changeEditable}
                  changeStatus={changeStatus}
                  changeBucket={changeBucket}
                  update={update}
                />
              )}
              {tab === 'versions' && (
                <VersionsTab
                  document={document}
                  sortedVersions={sortedVersions}
                  downloadVersion={downloadVersion}
                  handleNewVersion={handleNewVersion}
                  uploadVersion={uploadVersion}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Danger zone footer */}
        <div className="border-t border-border p-3">
          {isArchived ? (
            <Button variant="secondary" onClick={restore} loading={update.isPending} className="w-full">
              Restore document
            </Button>
          ) : (
            <Button variant="danger" onClick={() => setConfirmArchive(true)} className="w-full">
              Archive document
            </Button>
          )}
        </div>
      </div>

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

function OverviewTab({
  document,
  currentVersion,
}: {
  document: DocumentResponse
  currentVersion?: DocumentResponse['versions'][number]
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
  locked,
  isArchived,
  titleInput,
  setTitleInput,
  tagsInput,
  setTagsInput,
  saveTitle,
  saveTags,
  changeEditable,
  changeStatus,
  changeBucket,
  update,
}: {
  document: DocumentResponse
  buckets: BucketResponse[]
  locked: boolean
  isArchived: boolean
  titleInput: string
  setTitleInput: (v: string) => void
  tagsInput: string
  setTagsInput: (v: string) => void
  saveTitle: () => Promise<void> | undefined
  saveTags: () => Promise<void> | undefined
  changeEditable: (checked: boolean) => Promise<void>
  changeStatus: (status: string) => Promise<void>
  changeBucket: (value: string) => Promise<void>
  update: ReturnType<typeof useUpdateDocument>
}) {
  const isTitleUnchanged = !titleInput.trim() || titleInput.trim() === document.title

  return (
    <div className="flex flex-col gap-4">
      {/* Inline Title edit */}
      <Field label="Name" hint={locked ? 'Locked — enable editing to rename' : undefined}>
        <div className="flex gap-2">
          <Input
            value={titleInput}
            onChange={(e) => setTitleInput(e.target.value)}
            disabled={isArchived || locked}
            placeholder="Document name"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={saveTitle}
            disabled={isArchived || locked || isTitleUnchanged || update.isPending}
          >
            Save
          </Button>
        </div>
      </Field>

      {/* Editable toggle */}
      <Field
        label="Editable"
        hint="When off, the file is locked: no new versions, renaming, tags or bucket changes."
      >
        <Switch
          checked={document.is_editable}
          onChange={changeEditable}
          disabled={isArchived || update.isPending}
          label={document.is_editable ? 'Editable' : 'Locked'}
        />
      </Field>

      {/* Status picker */}
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

      {/* Bucket selector */}
      <Field label="Bucket">
        <Select
          value={document.bucket_id ?? ''}
          onChange={(e) => changeBucket(e.target.value)}
          disabled={update.isPending || isArchived || locked}
        >
          <option value="">Uncategorized</option>
          {buckets.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </Select>
      </Field>

      {/* Tags editor */}
      <Field label="Tags" hint="Comma-separated">
        <div className="flex gap-2">
          <Input
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="board, 2026"
            disabled={isArchived || locked}
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={saveTags}
            disabled={isArchived || locked || update.isPending}
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
  downloadVersion,
  handleNewVersion,
  uploadVersion,
}: {
  document: DocumentResponse
  sortedVersions: DocumentResponse['versions']
  downloadVersion: (versionId: string, filename: string) => void
  handleNewVersion: (files: File[]) => void
  uploadVersion: ReturnType<typeof useUploadVersion>
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
                onClick={() => downloadVersion(v.id, v.original_filename)}
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
  )
}
