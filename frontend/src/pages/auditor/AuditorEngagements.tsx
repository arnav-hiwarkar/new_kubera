import { useNavigate } from 'react-router-dom'
import { Briefcase, Layers, MailOpen, CheckCircle2, Archive } from 'lucide-react'
import { PageHeader, DataTable, StatusBadge, StatCard, Button, useToast, type Column } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { AuditEngagementResponse } from '@/api/types'
import { useAuditorEngagements, useAcceptEngagement } from '@/api/hooks/auditorEngagements'

export function AuditorEngagements() {
  const navigate = useNavigate()
  const toast = useToast()
  const { data = [], isLoading } = useAuditorEngagements()
  const accept = useAcceptEngagement()

  const doAccept = async (id: string) => {
    try {
      await accept.mutateAsync(id)
      toast.success('Engagement accepted')
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not accept')
    }
  }

  const columns: Column<AuditEngagementResponse>[] = [
    {
      key: 'period_label',
      header: 'Engagement',
      sortValue: (e) => e.period_label.toLowerCase(),
      cell: (e) => <span className="font-medium text-text-primary">{e.period_label}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (e) => e.status,
      cell: (e) => <StatusBadge status={e.status} />,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      cell: (e) => (
        <div className="flex justify-end gap-1" onClick={(ev) => ev.stopPropagation()}>
          {e.status === 'invited' ? (
            <Button size="sm" onClick={() => doAccept(e.id)} loading={accept.isPending}>
              Accept
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => navigate(`/auditor/app/${e.id}`)}>
              Open
            </Button>
          )}
        </div>
      ),
    },
  ]

  const total = data.length
  const invited = data.filter((e) => e.status === 'invited').length
  const active = data.filter((e) => e.status === 'active').length
  const closed = data.filter((e) => e.status === 'closed').length

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="ENGAGEMENTS"
        icon={<Briefcase />}
        title="Engagements"
        description="Audit engagements you have been invited to or are working on."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total" value={total} icon={<Layers />} tone="neutral" loading={isLoading} />
        <StatCard label="Invited" value={invited} icon={<MailOpen />} tone="info" loading={isLoading} />
        <StatCard label="Active" value={active} icon={<CheckCircle2 />} tone="info" loading={isLoading} />
        <StatCard label="Closed" value={closed} icon={<Archive />} tone="neutral" loading={isLoading} />
      </div>

      <DataTable
        columns={columns}
        data={data}
        rowKey={(e) => e.id}
        loading={isLoading}
        onRowClick={(e) => e.status !== 'invited' && navigate(`/auditor/app/${e.id}`)}
        emptyTitle="No engagements"
        emptyDescription="Engagements you are invited to will appear here."
      />
    </div>
  )
}
