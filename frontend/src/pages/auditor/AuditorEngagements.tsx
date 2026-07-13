import { useQuery } from '@tanstack/react-query'
import { auditorEngagementsApi } from '@/api/endpoints/auditorEngagements'
import type { AuditEngagementResponse } from '@/api/types'
import { PageHeader, DataTable, StatusBadge, type Column } from '@/components/ui'

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
]

export function AuditorEngagements() {
  const { data, isLoading } = useQuery({
    queryKey: ['auditor', 'engagements'],
    queryFn: () => auditorEngagementsApi.listEngagements(),
  })

  return (
    <div>
      <PageHeader
        title="Engagements"
        description="Audit engagements you have been invited to or are working on"
      />
      <DataTable
        columns={columns}
        data={data ?? []}
        rowKey={(e) => e.id}
        loading={isLoading}
        emptyTitle="No engagements"
        emptyDescription="Engagements you are invited to will appear here."
      />
    </div>
  )
}
