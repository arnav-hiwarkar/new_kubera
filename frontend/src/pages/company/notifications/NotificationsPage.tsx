import { PageHeader, Button } from '@/components/ui'
import { formatDate } from '@/lib/format'
import { useNotifications, useMarkNotificationRead } from '@/api/hooks/notifications'
import type { NotificationOut } from '@/api/types'

function NotificationItem({ notification }: { notification: NotificationOut }) {
  const markRead = useMarkNotificationRead()
  const isUnread = !notification.read_at
  const payload = notification.payload as Record<string, string> | undefined
  const message = payload?.message || notification.type

  return (
    <div
      className={`p-4 border rounded-xl flex items-start justify-between gap-4 transition-colors ${
        isUnread ? 'bg-bg-surface border-primary-500/20' : 'bg-bg-base border-border-base'
      }`}
    >
      <div>
        <div className="flex items-center gap-2 mb-1">
          {isUnread && <span className="w-2 h-2 rounded-full bg-primary-500" />}
          <span className="font-medium text-text-base">{message}</span>
        </div>
        <div className="text-sm text-text-secondary">
          {formatDate(notification.created_at)}
        </div>
      </div>
      {isUnread && (
        <Button
          variant="ghost"
          size="sm"
          loading={markRead.isPending}
          onClick={() => markRead.mutate(notification.id)}
        >
          Mark as read
        </Button>
      )}
    </div>
  )
}

export function NotificationsPage() {
  const { data: notifications, isLoading } = useNotifications()

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader
        title="Notifications"
        description="Stay updated on important events in your workspace."
      />
      {isLoading ? (
        <div className="animate-pulse space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-bg-surface rounded-xl" />
          ))}
        </div>
      ) : notifications?.length === 0 ? (
        <div className="text-center py-12 text-text-secondary">No notifications yet.</div>
      ) : (
        <div className="space-y-4">
          {notifications?.map((n) => (
            <NotificationItem key={n.id} notification={n} />
          ))}
        </div>
      )}
    </div>
  )
}
