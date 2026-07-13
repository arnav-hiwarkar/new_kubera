import { useState } from 'react'
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

  const item = (key: BucketSelection, label: string, count: number, deletable?: BucketResponse) => (
    <li key={key} className="group flex items-center">
      <button
        onClick={() => onSelect(key)}
        className={cn(
          'flex flex-1 items-center justify-between rounded-btn px-2 py-1.5 text-left text-sm',
          selected === key
            ? 'bg-accent-subtle font-medium text-accent'
            : 'text-text-secondary hover:bg-bg-raised hover:text-text-primary',
        )}
      >
        <span className="truncate">{label}</span>
        <span className="ml-2 shrink-0 text-xs text-text-muted">{count}</span>
      </button>
      {deletable && (
        <button
          onClick={() => setToDelete(deletable)}
          aria-label={`Delete bucket ${deletable.name}`}
          className="ml-1 hidden px-1 text-text-muted hover:text-status-action group-hover:block"
        >
          ×
        </button>
      )}
    </li>
  )

  return (
    <div className="flex w-56 shrink-0 flex-col rounded-card border border-border bg-bg-surface p-2">
      <div className="mb-1 flex items-center justify-between px-2 py-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          Buckets
        </span>
        <button
          onClick={() => setCreating((c) => !c)}
          className="text-sm text-accent hover:underline"
        >
          + New
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
        {item('all', 'All Documents', activeCount)}
        {item('uncategorized', 'Uncategorized', uncategorizedCount)}
        <li className="my-1 border-t border-border" />
        {buckets.map((b) => item(b.id, b.name, countFor(b.id), b))}
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
