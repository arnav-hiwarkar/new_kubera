import { useMemo, useState } from 'react'
import { Button, Input, Spinner, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { TrialBalanceAccountResponse } from '@/api/types'
import {
  useCompanyTrialBalance,
  useLedgerGroups,
  useMapLedger,
  useBulkMapLedgers,
  useUnmapLedgers,
} from '@/api/hooks/auditease'
import { GroupTree } from './GroupTree'
import { GroupPicker } from '@/components/auditease/GroupPicker'
import { ImportMappingModal } from './ImportMappingModal'

export function MappingTab({ engagementId }: { engagementId: string }) {
  const toast = useToast()
  const { data: accounts = [], isLoading } = useCompanyTrialBalance(engagementId)
  const { data: groups = [] } = useLedgerGroups()
  const mapLedger = useMapLedger()
  const bulkMap = useBulkMapLedgers()
  const unmap = useUnmapLedgers()

  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkLeaf, setBulkLeaf] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return accounts
    return accounts.filter(
      (a) => a.ledger_name.toLowerCase().includes(q) || (a.ledger_code ?? '').toLowerCase().includes(q),
    )
  }, [accounts, query])

  const toggleRow = (id: string) =>
    setSelected((s) => {
      const next = new Set(s)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const mappedCount = accounts.filter((a) => a.mapped_group_id).length
  const totalCount = accounts.length
  const pct = totalCount ? Math.round((mappedCount / totalCount) * 100) : 0

  const allVisibleSelected = filtered.length > 0 && filtered.every((a) => selected.has(a.id))
  const toggleAll = () =>
    setSelected((s) => {
      const next = new Set(s)
      if (allVisibleSelected) filtered.forEach((a) => next.delete(a.id))
      else filtered.forEach((a) => next.add(a.id))
      return next
    })

  const handleRowMap = async (row: TrialBalanceAccountResponse, leafId: string | null) => {
    if (!leafId || leafId === row.mapped_group_id) return
    try {
      await mapLedger.mutateAsync({ engagementId, ledgerId: row.id, groupId: leafId })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not map')
    }
  }

  const handleRowUnmap = async (row: TrialBalanceAccountResponse) => {
    try {
      await unmap.mutateAsync({ engagementId, body: { ledger_ids: [row.id] } })
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not unmap')
    }
  }

  const applyBulk = async () => {
    if (!bulkLeaf || selected.size === 0) return
    try {
      const res = await bulkMap.mutateAsync({
        engagementId,
        body: { ledger_ids: [...selected], group_id: bulkLeaf },
      })
      toast.success(`Mapped ${res.updated} ledgers`)
      setSelected(new Set())
      setBulkLeaf(null)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Bulk map failed')
    }
  }

  const unmapBulk = async () => {
    if (selected.size === 0) return
    try {
      const res = await unmap.mutateAsync({ engagementId, body: { ledger_ids: [...selected] } })
      toast.success(`Unmapped ${res.updated} ledgers`)
      setSelected(new Set())
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Unmap failed')
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
      <div>
        <h3 className="mb-2 text-sm font-semibold text-text-primary">Chart of accounts</h3>
        <p className="mb-3 text-xs text-text-muted">
          Subgroups you create here are shared across all engagements.
        </p>
        <GroupTree />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-text-primary">
            Ledgers <span className="text-text-muted">({accounts.length})</span>
          </h3>
          <div className="flex items-center gap-2">
            {accounts.length > 0 && (
              <Button size="sm" variant="secondary" onClick={() => setImportOpen(true)}>
                Import mapping
              </Button>
            )}
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search ledgers…"
              className="h-8 max-w-xs"
            />
          </div>
        </div>

        {totalCount > 0 && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-xs text-text-muted">
              <span>
                {mappedCount}/{totalCount} ledgers mapped
              </span>
              <span>{pct}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-raised">
              <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        {selected.size > 0 && (
          <div className="flex flex-wrap items-center gap-2 rounded-card border border-accent/40 bg-accent-subtle px-3 py-2">
            <span className="text-sm font-medium text-text-primary">{selected.size} selected</span>
            <GroupPicker groups={groups} value={bulkLeaf} onChange={setBulkLeaf} />
            <Button size="sm" onClick={applyBulk} loading={bulkMap.isPending} disabled={!bulkLeaf}>
              Map selected
            </Button>
            <Button size="sm" variant="secondary" onClick={unmapBulk} loading={unmap.isPending}>
              Unmap
            </Button>
            <button className="text-xs text-text-muted hover:text-text-primary" onClick={() => setSelected(new Set())}>
              Clear
            </button>
          </div>
        )}

        {isLoading ? (
          <Spinner className="mx-auto mt-8 h-6 w-6" />
        ) : accounts.length === 0 ? (
          <p className="rounded-card border border-border bg-bg-surface p-6 text-center text-sm text-text-muted">
            Import a trial balance first, then map its ledgers here.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-card border border-border bg-bg-surface">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-bg-raised/50 text-text-secondary">
                <tr>
                  <th className="w-8 px-3 py-2">
                    <input type="checkbox" checked={allVisibleSelected} onChange={toggleAll} />
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide">Ledger</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide">Mapping</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={selected.has(row.id)}
                        onChange={() => toggleRow(row.id)}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium text-text-primary">{row.ledger_name}</div>
                      {row.ledger_code && <div className="text-xs text-text-muted">{row.ledger_code}</div>}
                      {row.mapped_group_path && (
                        <div className="text-xs text-status-verified">
                          {row.mapped_group_path.join(' › ')}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <GroupPicker
                        groups={groups}
                        value={row.mapped_group_id ?? null}
                        onChange={(leaf) => handleRowMap(row, leaf)}
                      />
                    </td>
                    <td className="px-3 py-2 text-right">
                      {row.mapped_group_id && (
                        <button
                          className="text-xs text-text-muted hover:text-status-action"
                          onClick={() => handleRowUnmap(row)}
                        >
                          Clear
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <ImportMappingModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        engagementId={engagementId}
        mappedTargetCount={mappedCount}
      />
    </div>
  )
}
