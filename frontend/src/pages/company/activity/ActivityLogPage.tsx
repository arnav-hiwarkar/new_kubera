import { History } from 'lucide-react'
import { PageHeader, DataTable, StatusBadge } from '@/components/ui'
import { formatDate, formatRelative } from '@/lib/format'
import { useActivityLog } from '@/api/hooks/activity'
import type { ActivityLogOut } from '@/api/types'

function humanize(str: string) {
  return str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function ActivityLogPage() {
  const { data: logs, isLoading } = useActivityLog()

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="SYSTEM"
        icon={<History />}
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
            cell: (log) => (
              <div className="flex items-start gap-3">
                <span
                  className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent ring-4 ring-accent-subtle"
                  aria-hidden
                />
                <div className="leading-tight">
                  <div className="text-sm font-medium text-text-primary">
                    {formatRelative(log.created_at)}
                  </div>
                  <div className="text-xs text-text-muted">{formatDate(log.created_at)}</div>
                </div>
              </div>
            ),
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
            cell: (log) => (
              <span className="font-medium text-text-primary">{humanize(log.action)}</span>
            ),
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
