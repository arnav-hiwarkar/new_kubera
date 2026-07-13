import { PageHeader, DataTable, StatusBadge } from '@/components/ui'
import { formatDate } from '@/lib/format'
import { useActivityLog } from '@/api/hooks/activity'
import type { ActivityLogOut } from '@/api/types'

function humanize(str: string) {
  return str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function ActivityLogPage() {
  const { data: logs, isLoading } = useActivityLog()

  return (
    <div className="space-y-6">
      <PageHeader
        title="Activity Log"
        description="A complete audit trail of actions taken in your company workspace."
      />
      <DataTable
        data={logs || []}
        loading={isLoading}
        rowKey={(row) => row.id}
        emptyTitle="No activity found"
        searchAccessors={(row: ActivityLogOut) => `${row.action} ${row.entity_type}`}
        columns={[
          {
            key: 'timestamp',
            header: 'Timestamp',
            cell: (log) => formatDate(log.created_at),
          },
          {
            key: 'user',
            header: 'User',
            cell: (log) => (
              <span className="text-sm font-mono text-text-secondary">
                {log.actor_id.split('-')[0]}
              </span>
            ),
          },
          {
            key: 'action',
            header: 'Action',
            cell: (log) => humanize(log.action),
          },
          {
            key: 'entity',
            header: 'Entity Type',
            cell: (log) => (
              <StatusBadge tone="neutral" status={humanize(log.entity_type)} />
            ),
          },
        ]}
      />
    </div>
  )
}
