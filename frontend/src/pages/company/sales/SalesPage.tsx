import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingUp } from 'lucide-react'
import { PageHeader, Button, DataTable, StatusBadge, StatCard, Select, useToast, type Column } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { useSales, useSalesAggregate } from '@/api/hooks/sales'
import { useCustomFields } from '@/api/hooks/customFields'
import { salesApi } from '@/api/endpoints/sales'
import { usersApi } from '@/api/endpoints/users'
import { SALES_STATUS, humanize } from '@/api/enums'
import { formatMoney } from '@/lib/format'
import { saveBlob } from '@/lib/download'
import type { SalesRecordResponse } from '@/api/types'
import { SalesDrawer } from './SalesDrawer'
import { ImportSalesModal } from './ImportSalesModal'

export function SalesPage() {
  const { profile } = useCompanyAuth()
  const me = profile ? { id: profile.id, role: profile.role } : null
  const toast = useToast()

  const [status, setStatus] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selected, setSelected] = useState<SalesRecordResponse | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const filters = { ...(status ? { status } : {}) }
  const { data: sales = [], isLoading } = useSales(filters)
  const { data: aggregate = [] } = useSalesAggregate()
  const { data: activeFields = [] } = useCustomFields('sales_tracking', false)

  // Role-scoped owner directory: admins see everyone, managers see their
  // direct reports, employees fetch nothing (owner is implicitly self).
  const usersQuery = useQuery({
    queryKey: ['sales', 'directory', me?.role],
    queryFn: () => (me?.role === 'admin' ? usersApi.list() : usersApi.myReports()),
    enabled: !!me && (me.role === 'admin' || me.role === 'manager'),
  })

  const visibleUsers = useMemo(() => usersQuery.data ?? [], [usersQuery.data])
  const nameById = useMemo(() => {
    const m: Record<string, string> = {}
    for (const u of visibleUsers) m[u.id] = u.full_name
    if (profile) m[profile.id] = profile.full_name
    return m
  }, [visibleUsers, profile])

  const openCreate = () => {
    setSelected(null)
    setDrawerOpen(true)
  }
  const openSale = (s: SalesRecordResponse) => {
    setSelected(s)
    setDrawerOpen(true)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await salesApi.exportExcel()
      saveBlob(blob, 'sales.xlsx')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const columns: Column<SalesRecordResponse>[] = [
    {
      key: 'client_name',
      header: 'Client',
      sortValue: (s) => s.client_name.toLowerCase(),
      cell: (s) => (
        <div>
          <div className="font-medium text-text-primary">{s.client_name}</div>
          <div className="text-xs text-text-muted">{s.product_service}</div>
        </div>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      sortValue: (s) => s.amount,
      cell: (s) => formatMoney(s.amount),
    },
    { key: 'status', header: 'Status', sortValue: (s) => s.status, cell: (s) => <StatusBadge status={s.status} /> },
    { key: 'owner', header: 'Owner', cell: (s) => nameById[s.user_id] ?? '—' },
    { key: 'closing_date', header: 'Closing date', sortValue: (s) => s.closing_date ?? '', cell: (s) => s.closing_date || '—' },
  ]

  if (!me) return null

  const statusTone: Record<(typeof SALES_STATUS)[number], 'gold' | 'accent' | 'info'> = {
    lead: 'info',
    negotiation: 'accent',
    won: 'gold',
    lost: 'info',
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="OPERATIONS"
        icon={<TrendingUp />}
        title="Sales"
        description="Sales pipeline and deal log"
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setImportOpen(true)}>Import</Button>
            <Button variant="secondary" onClick={handleExport} loading={exporting}>Export</Button>
            <Button onClick={openCreate}>New sale</Button>
          </div>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {SALES_STATUS.map((s) => {
          const row = aggregate.find((r) => r.status === s)
          return (
            <StatCard
              key={s}
              label={humanize(s)}
              value={row?.count ?? 0}
              tone={statusTone[s]}
              sub={
                <span className="font-mono tabular-nums">{formatMoney(row?.total_amount ?? 0)}</span>
              }
            />
          )
        })}
      </div>

      <div className="flex flex-wrap gap-2">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 max-w-[180px]">
          <option value="">All statuses</option>
          {SALES_STATUS.map((s) => (
            <option key={s} value={s}>{humanize(s)}</option>
          ))}
        </Select>
      </div>

      <DataTable
        columns={columns}
        data={sales}
        rowKey={(s) => s.id}
        loading={isLoading}
        onRowClick={openSale}
        searchAccessors={(s) => `${s.client_name} ${s.product_service}`}
        searchPlaceholder="Search sales…"
        emptyTitle="No sales"
        emptyDescription="Create or import a sale to get started."
      />

      <SalesDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sale={selected}
        me={me}
        users={visibleUsers}
        activeFields={activeFields}
      />
      <ImportSalesModal open={importOpen} onClose={() => setImportOpen(false)} activeFields={activeFields} />
    </div>
  )
}
