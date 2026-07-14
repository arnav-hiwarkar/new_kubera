import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Target, Clock, Activity, CheckCircle2 } from 'lucide-react'
import { PageHeader, Button, DataTable, StatusBadge, StatCard, Tabs, type Column } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { useKras } from '@/api/hooks/kra'
import { usersApi } from '@/api/endpoints/users'
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

  const countBy = (status: string) => rows.filter((k) => k.status === status).length

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="WORKFORCE"
        icon={<Target />}
        title="KRA & Appraisals"
        description="Key result areas and the plan, progress and appraisal cycle"
        actions={
          tab === 'mine' ? <Button onClick={openCreate}>New KRA</Button> : undefined
        }
      />

      <Tabs
        tabs={tabs}
        value={tab}
        onChange={(id) => setTab(id as Tab)}
        accent="company"
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Total KRAs" value={rows.length} icon={<Target />} tone="accent" loading={isLoading} />
        <StatCard label="Pending approval" value={countBy('pending_approval')} icon={<Clock />} tone="warning" loading={isLoading} />
        <StatCard label="In progress" value={countBy('in_progress')} icon={<Activity />} tone="info" loading={isLoading} />
        <StatCard label="Completed" value={countBy('completed')} icon={<CheckCircle2 />} tone="accent" loading={isLoading} />
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
