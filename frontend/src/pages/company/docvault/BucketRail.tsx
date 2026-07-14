import { useState, type ComponentType } from 'react'
import { Files, Folder, FolderOpen, Plus, X } from 'lucide-react'
import { cn } from '@/lib/cn'
import { Button, Input, ConfirmDialog, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { BucketResponse, DocumentResponse } from '@/api/types'
import { useCreateBucket, useDeleteBucket } from '@/api/hooks/docvault'

export type BucketSelection = 'all' | 'uncategorized' | string

export interface BucketRailProps {
  buckets: BucketResponse[]
  documents: DocumentResponse[]
  selected: BucketSelection
  onSelect: (selection: BucketSelection) => void
}

export function BucketRail({ buckets, documents, selected, onSelect }: BucketRailProps) {
  const toast = useToast()
  const createBucket = useCreateBucket()
  const deleteBucket = useDeleteBucket()

  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [toDelete, setToDelete] = useState<BucketResponse | null>(null)

  const activeCount = documents.filter((d) => d.status !== 'archived').length
  const uncategorizedCount = documents.filter(
    (d) => !d.bucket_id && d.status !== 'archived',
  ).length
  const countFor = (id: string) =>
    documents.filter((d) => d.bucket_id === id && d.status !== 'archived').length

  const submitCreate = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      await createBucket.mutateAsync(name)
      toast.success('Bucket created')
      setNewName('')
      setCreating(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not create bucket')
    }
  }

  const confirmDelete = async () => {
    if (!toDelete) return
    try {
      await deleteBucket.mutateAsync(toDelete.id)
      toast.success('Bucket deleted')
      if (selected === toDelete.id) onSelect('all')
      setToDelete(null)
    } catch (err) {
      // Backend returns 400 when the bucket still holds documents.
      toast.error(err instanceof ApiError ? err.message : 'Could not delete bucket')
      setToDelete(null)
    }
  }

  const item = (
    key: BucketSelection,
    label: string,
    count: number,
    Icon: ComponentType<{ className?: string }>,
    deletable?: BucketResponse,
  ) => {
    const active = selected === key
    return (
      <li key={key} className="group flex items-center">
        <button
          onClick={() => onSelect(key)}
          className={cn(
            'flex flex-1 items-center gap-2 rounded-btn px-2 py-1.5 text-left text-sm transition-colors',
            active
              ? 'bg-accent-subtle font-medium text-accent'
              : 'text-text-secondary hover:bg-bg-raised hover:text-text-primary',
          )}
        >
          <Icon className="h-4 w-4 shrink-0" />
          <span className="truncate">{label}</span>
          <span
            className={cn(
              'ml-auto shrink-0 rounded-pill px-1.5 py-0.5 text-xs font-semibold tabular-nums',
              active ? 'bg-accent/15 text-accent' : 'bg-bg-raised text-text-muted',
            )}
          >
            {count}
          </span>
        </button>
        {deletable && (
          <button
            onClick={() => setToDelete(deletable)}
            aria-label={`Delete bucket ${deletable.name}`}
            className="ml-1 hidden text-text-muted hover:text-status-action group-hover:block"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </li>
    )
  }

  return (
    <div className="flex w-56 shrink-0 flex-col rounded-card border border-border bg-bg-surface p-2">
      <div className="mb-1 flex items-center justify-between px-2 py-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Buckets
        </span>
        <button
          onClick={() => setCreating((c) => !c)}
          className="flex items-center gap-1 text-sm text-accent hover:underline"
        >
          <Plus className="h-3.5 w-3.5" />
          New
        </button>
      </div>

      {creating && (
        <div className="mb-2 flex gap-1 px-1">
          <Input
            autoFocus
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submitCreate()
              if (e.key === 'Escape') setCreating(false)
            }}
            placeholder="Bucket name"
            className="h-8"
          />
          <Button size="sm" onClick={submitCreate} loading={createBucket.isPending}>
            Add
          </Button>
        </div>
      )}

      <ul className="flex flex-col gap-0.5">
        {item('all', 'All Documents', activeCount, Files)}
        {item('uncategorized', 'Uncategorized', uncategorizedCount, FolderOpen)}
        <li className="my-1 border-t border-border" />
        {buckets.map((b) => item(b.id, b.name, countFor(b.id), Folder, b))}
      </ul>

      <ConfirmDialog
        open={!!toDelete}
        title="Delete bucket?"
        message={`Delete "${toDelete?.name}"? Buckets must be empty first — documents inside must be moved or archived.`}
        confirmLabel="Delete"
        destructive
        loading={deleteBucket.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setToDelete(null)}
      />
    </div>
  )
}
