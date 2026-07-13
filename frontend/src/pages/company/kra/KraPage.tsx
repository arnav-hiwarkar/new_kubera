import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader, Button, DataTable, StatusBadge, type Column } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { useKras } from '@/api/hooks/kra'
import { usersApi } from '@/api/endpoints/users'
import { cn } from '@/lib/cn'
import type { KRAResponse } from '@/api/types'
import { KraDrawer } from './KraDrawer'

type Tab = 'mine' | 'team'

export function KraPage() {
  const { profile } = useCompanyAuth()
  const me = profile ? { id: profile.id, role: profile.role } : null

  const [tab, setTab] = useState<Tab>('mine')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selected, setSelected] = useState<KRAResponse | null>(null)

  const { data: kras = [], isLoading } = useKras()

  const isManagerOrAdmin = me?.role === 'manager' || me?.role === 'admin'

  // Directory for resolving owner names on the Team tab (admins see everyone,
  // managers see their direct reports).
  const directory = useQuery({
    queryKey: ['kra', 'directory', me?.role],
    queryFn: () => (me?.role === 'admin' ? usersApi.list() : usersApi.myReports()),
    enabled: !!me && isManagerOrAdmin,
  })
  const nameById = useMemo(() => {
    const map: Record<string, string> = {}
    for (const u of directory.data ?? []) map[u.id] = u.full_name
    if (profile) map[profile.id] = profile.full_name
    return map
  }, [directory.data, profile])

  const cycles = useMemo(
    () => [...new Set(kras.map((k) => k.cycle))].sort(),
    [kras],
  )

  const mine = useMemo(() => kras.filter((k) => k.user_id === me?.id), [kras, me?.id])
  const team = useMemo(() => kras.filter((k) => k.user_id !== me?.id), [kras, me?.id])

  const openCreate = () => {
    setSelected(null)
    setDrawerOpen(true)
  }
  const openKra = (k: KRAResponse) => {
    setSelected(k)
    setDrawerOpen(true)
  }

  const baseCols: Column<KRAResponse>[] = [
    {
      key: 'title',
      header: 'Title',
      sortValue: (k) => k.title.toLowerCase(),
      cell: (k) => (
        <div>
          <div className="font-medium text-text-primary">{k.title}</div>
          {k.target_metric && <div className="text-xs text-text-muted">Target: {k.target_metric}</div>}
        </div>
      ),
    },
    { key: 'cycle', header: 'Cycle', sortValue: (k) => k.cycle, cell: (k) => k.cycle },
    {
      key: 'weightage',
      header: 'Weightage',
      align: 'right',
      sortValue: (k) => k.weightage,
      cell: (k) => k.weightage,
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (k) => k.status,
      cell: (k) => <StatusBadge status={k.status} />,
    },
  ]

  const teamCols: Column<KRAResponse>[] = [
    {
      key: 'employee',
      header: 'Employee',
      sortValue: (k) => nameById[k.user_id] ?? '',
      cell: (k) => nameById[k.user_id] ?? '—',
    },
    ...baseCols,
  ]

  if (!me) return null

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: 'mine', label: 'My KRAs', count: mine.length },
    ...(isManagerOrAdmin ? [{ id: 'team' as Tab, label: 'Team', count: team.length }] : []),
  ]

  const rows = tab === 'mine' ? mine : team
  const columns = tab === 'mine' ? baseCols : teamCols

  return (
    <div>
      <PageHeader
        title="KRA & Appraisals"
        description="Key result areas and the plan → progress → appraisal cycle"
        actions={
          tab === 'mine' ? <Button onClick={openCreate}>New KRA</Button> : undefined
        }
      />

      <div className="mb-4 flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === t.id
                ? 'border-accent text-text-primary'
                : 'border-transparent text-text-muted hover:text-text-primary',
            )}
          >
            {t.label} <span className="text-text-muted">({t.count})</span>
          </button>
        ))}
      </div>

      <DataTable
        columns={columns}
        data={rows}
        rowKey={(k) => k.id}
        loading={isLoading}
        onRowClick={openKra}
        searchAccessors={(k) => `${k.title} ${k.cycle} ${nameById[k.user_id] ?? ''}`}
        searchPlaceholder="Search KRAs…"
        emptyTitle={tab === 'mine' ? 'No KRAs yet' : 'No team KRAs'}
        emptyDescription={
          tab === 'mine'
            ? 'Create a KRA to start a review cycle.'
            : 'Your reports have no KRAs in view yet.'
        }
      />

      <KraDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        kra={selected}
        me={me}
        cycles={cycles}
        ownerName={selected ? nameById[selected.user_id] : undefined}
      />
    </div>
  )
}
