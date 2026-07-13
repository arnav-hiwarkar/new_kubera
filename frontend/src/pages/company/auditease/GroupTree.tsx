import { useMemo, useState } from 'react'
import { Button, Input, ConfirmDialog, useToast } from '@/components/ui'
import { cn } from '@/lib/cn'
import { ApiError } from '@/api/http'
import type { LedgerGroupResponse } from '@/api/types'
import {
  useLedgerGroups,
  useCreateLedgerGroup,
  useRenameLedgerGroup,
  useDeleteLedgerGroup,
} from '@/api/hooks/auditease'

const byName = (a: LedgerGroupResponse, b: LedgerGroupResponse) => a.name.localeCompare(b.name)

export function GroupTree() {
  const toast = useToast()
  const { data: groups = [], isLoading } = useLedgerGroups()
  const createGroup = useCreateLedgerGroup()
  const renameGroup = useRenameLedgerGroup()
  const deleteGroup = useDeleteLedgerGroup()

  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [addingUnder, setAddingUnder] = useState<string | null>(null)
  const [addName, setAddName] = useState('')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<LedgerGroupResponse | null>(null)

  const childrenOf = (pid: string | null) =>
    groups.filter((g) => g.parent_id === pid).sort(byName)
  const tops = useMemo(() => groups.filter((g) => g.level === 0).sort(byName), [groups])

  // Search: keep a node if it or any descendant matches; force-expand while searching.
  const q = query.trim().toLowerCase()
  const matchIds = useMemo(() => {
    if (!q) return null
    const keep = new Set<string>()
    const subtreeMatches = (node: LedgerGroupResponse): boolean => {
      const kids = groups.filter((g) => g.parent_id === node.id)
      const self = node.name.toLowerCase().includes(q)
      const childHit = kids.some(subtreeMatches)
      if (self || childHit) keep.add(node.id)
      return self || childHit
    }
    tops.forEach(subtreeMatches)
    return keep
  }, [q, groups, tops])

  const isOpen = (id: string) => (q ? true : !!expanded[id])
  const toggle = (id: string) =>
    setExpanded((e) => ({ ...e, [id]: !e[id] }))

  const submitAdd = async (parentId: string) => {
    const name = addName.trim()
    if (!name) return
    try {
      await createGroup.mutateAsync({ name, parent_id: parentId })
      setAddName('')
      setAddingUnder(null)
      setExpanded((e) => ({ ...e, [parentId]: true }))
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not create group')
    }
  }

  const submitRename = async (id: string) => {
    const name = renameValue.trim()
    if (!name) return
    try {
      await renameGroup.mutateAsync({ id, body: { name } })
      setRenaming(null)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not rename')
    }
  }

  const doDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteGroup.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not delete')
    }
  }

  const renderNode = (node: LedgerGroupResponse) => {
    if (matchIds && !matchIds.has(node.id)) return null
    const kids = childrenOf(node.id)
    const owned = node.company_id !== null
    const canAddChild = node.level < 2
    const open = isOpen(node.id)

    return (
      <li key={node.id}>
        <div
          className="group flex items-center gap-1 rounded-btn px-1.5 py-1 hover:bg-bg-raised/60"
          style={{ paddingLeft: `${node.level * 16 + 6}px` }}
        >
          {kids.length > 0 ? (
            <button
              onClick={() => toggle(node.id)}
              className="w-4 text-text-muted"
              aria-label={open ? 'Collapse' : 'Expand'}
            >
              {open ? '▾' : '▸'}
            </button>
          ) : (
            <span className="w-4" />
          )}

          {renaming === node.id ? (
            <Input
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitRename(node.id)
                if (e.key === 'Escape') setRenaming(null)
              }}
              className="h-7 max-w-[16rem]"
              autoFocus
            />
          ) : (
            <span
              className={cn(
                'flex-1 text-sm',
                node.level === 0 ? 'font-semibold text-text-primary' : 'text-text-secondary',
              )}
            >
              {node.name}
              {node.level === 0 && <span className="ml-2 text-xs text-text-muted">(fixed)</span>}
            </span>
          )}

          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
            {canAddChild && (
              <button
                className="text-xs text-accent hover:underline"
                onClick={() => {
                  setAddingUnder(node.id)
                  setAddName('')
                  setExpanded((e) => ({ ...e, [node.id]: true }))
                }}
              >
                + {node.level === 0 ? 'subgroup' : 'subsubgroup'}
              </button>
            )}
            {owned && (
              <>
                <button
                  className="text-xs text-text-muted hover:text-text-primary"
                  onClick={() => {
                    setRenaming(node.id)
                    setRenameValue(node.name)
                  }}
                >
                  Rename
                </button>
                <button
                  className="text-xs text-status-action hover:underline"
                  onClick={() => setDeleteTarget(node)}
                >
                  Delete
                </button>
              </>
            )}
          </div>
        </div>

        {addingUnder === node.id && (
          <div className="flex items-center gap-2 py-1" style={{ paddingLeft: `${(node.level + 1) * 16 + 22}px` }}>
            <Input
              value={addName}
              onChange={(e) => setAddName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitAdd(node.id)
                if (e.key === 'Escape') setAddingUnder(null)
              }}
              placeholder={node.level === 0 ? 'New subgroup' : 'New subsubgroup'}
              className="h-7 max-w-[16rem]"
              autoFocus
            />
            <Button size="sm" onClick={() => submitAdd(node.id)} loading={createGroup.isPending}>
              Add
            </Button>
            <button className="text-xs text-text-muted" onClick={() => setAddingUnder(null)}>
              Cancel
            </button>
          </div>
        )}

        {open && kids.length > 0 && <ul>{kids.map(renderNode)}</ul>}
      </li>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search groups…"
        className="h-8"
      />
      <div className="rounded-card border border-border bg-bg-surface p-2">
        {isLoading ? (
          <p className="p-3 text-sm text-text-muted">Loading…</p>
        ) : (
          <ul>{tops.map(renderNode)}</ul>
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete group?"
        message={`Delete "${deleteTarget?.name}"? This is blocked if it has subgroups or mapped ledgers.`}
        confirmLabel="Delete"
        destructive
        loading={deleteGroup.isPending}
        onConfirm={doDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
