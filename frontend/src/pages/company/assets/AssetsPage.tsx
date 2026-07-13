import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader, Button, DataTable, StatusBadge, Select, useToast, type Column } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { useAssets } from '@/api/hooks/assets'
import { useCustomFields } from '@/api/hooks/customFields'
import { assetsApi } from '@/api/endpoints/assets'
import { usersApi } from '@/api/endpoints/users'
import { docvaultApi } from '@/api/endpoints/docvault'
import { ASSET_CATEGORY, ASSET_STATUS, humanize } from '@/api/enums'
import { formatMoney } from '@/lib/format'
import { saveBlob } from '@/lib/download'
import type { AssetResponse } from '@/api/types'
import { AssetDrawer } from './AssetDrawer'
import { ImportAssetsModal } from './ImportAssetsModal'

export function AssetsPage() {
  const { profile } = useCompanyAuth()
  const isAdmin = profile?.role === 'admin'
  const toast = useToast()

  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selected, setSelected] = useState<AssetResponse | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const filters = {
    ...(category ? { category } : {}),
    ...(status ? { status } : {}),
  }
  const { data: assets = [], isLoading } = useAssets(filters)

  // Admins can resolve custodian names + pick users/documents; non-admins cannot.
  const usersQuery = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list(), enabled: !!isAdmin })
  const docsQuery = useQuery({
    queryKey: ['docvault', 'documents'],
    queryFn: () => docvaultApi.listDocuments(),
    enabled: !!isAdmin,
  })
  const { data: activeFields = [] } = useCustomFields('asset_management', false)

  const users = useMemo(() => usersQuery.data ?? [], [usersQuery.data])
  const documents = docsQuery.data ?? []
  const nameById = useMemo(() => {
    const m: Record<string, string> = {}
    for (const u of users) m[u.id] = u.full_name
    if (profile) m[profile.id] = profile.full_name
    return m
  }, [users, profile])

  const custodianLabel = (id: string | null | undefined) => {
    if (!id) return 'Unassigned'
    return nameById[id] ?? (id === profile?.id ? profile.full_name : '—')
  }

  const openCreate = () => {
    setSelected(null)
    setDrawerOpen(true)
  }
  const openAsset = (a: AssetResponse) => {
    setSelected(a)
    setDrawerOpen(true)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await assetsApi.exportExcel()
      saveBlob(blob, 'assets.xlsx')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const columns: Column<AssetResponse>[] = [
    {
      key: 'asset_name',
      header: 'Asset',
      sortValue: (a) => a.asset_name.toLowerCase(),
      cell: (a) => (
        <div>
          <div className="font-medium text-text-primary">{a.asset_name}</div>
          {a.serial_number && <div className="text-xs text-text-muted">{a.serial_number}</div>}
        </div>
      ),
    },
    { key: 'category', header: 'Category', sortValue: (a) => a.category, cell: (a) => <StatusBadge status={a.category} /> },
    { key: 'status', header: 'Status', sortValue: (a) => a.status, cell: (a) => <StatusBadge status={a.status} /> },
    {
      key: 'purchase_cost',
      header: 'Purchase cost',
      align: 'right',
      sortValue: (a) => a.purchase_cost ?? 0,
      cell: (a) => (a.purchase_cost != null ? formatMoney(a.purchase_cost) : '—'),
    },
    { key: 'custodian', header: 'Custodian', cell: (a) => custodianLabel(a.custodian_id) },
  ]

  return (
    <div>
      <PageHeader
        title="Assets"
        description="Company asset register"
        actions={
          isAdmin ? (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setImportOpen(true)}>Import</Button>
              <Button variant="secondary" onClick={handleExport} loading={exporting}>Export</Button>
              <Button onClick={openCreate}>New asset</Button>
            </div>
          ) : undefined
        }
      />

      <div className="mb-3 flex flex-wrap gap-2">
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="h-8 max-w-[180px]">
          <option value="">All categories</option>
          {ASSET_CATEGORY.map((c) => (
            <option key={c} value={c}>{humanize(c)}</option>
          ))}
        </Select>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 max-w-[180px]">
          <option value="">All statuses</option>
          {ASSET_STATUS.map((s) => (
            <option key={s} value={s}>{humanize(s)}</option>
          ))}
        </Select>
      </div>

      <DataTable
        columns={columns}
        data={assets}
        rowKey={(a) => a.id}
        loading={isLoading}
        onRowClick={openAsset}
        searchAccessors={(a) => `${a.asset_name} ${a.serial_number ?? ''}`}
        searchPlaceholder="Search assets…"
        emptyTitle="No assets"
        emptyDescription={isAdmin ? 'Create or import assets to get started.' : 'No assets assigned to you.'}
      />

      <AssetDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        asset={selected}
        isAdmin={!!isAdmin}
        users={users}
        documents={documents}
        activeFields={activeFields}
      />
      {isAdmin && (
        <ImportAssetsModal open={importOpen} onClose={() => setImportOpen(false)} activeFields={activeFields} />
      )}
    </div>
  )
}
