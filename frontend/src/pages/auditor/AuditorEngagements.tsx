import { useNavigate } from 'react-router-dom'
import { PageHeader, DataTable, StatusBadge, Button, useToast, type Column } from '@/components/ui'
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

  return (
    <div>
      <PageHeader
        title="Engagements"
        description="Audit engagements you have been invited to or are working on."
      />
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
