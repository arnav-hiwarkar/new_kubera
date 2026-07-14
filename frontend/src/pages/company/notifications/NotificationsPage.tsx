import { useMemo } from 'react'
import { Bell, CheckCheck, AlertTriangle, Info, CheckCircle2, FileText } from 'lucide-react'
import { PageHeader, Button, EmptyState } from '@/components/ui'
import { formatRelative } from '@/lib/format'
import { useNotifications, useMarkNotificationRead } from '@/api/hooks/notifications'
import type { NotificationOut } from '@/api/types'

function iconFor(type: string) {
  const t = type.toLowerCase()
  if (t.includes('alert') || t.includes('warn') || t.includes('overdue')) return AlertTriangle
  if (t.includes('success') || t.includes('verified') || t.includes('approved')) return CheckCircle2
  if (t.includes('document') || t.includes('doc') || t.includes('upload')) return FileText
  return Info
}

function NotificationItem({
  notification,
  onMarkRead,
  pending,
}: {
  notification: NotificationOut
  onMarkRead: (id: string) => void
  pending: boolean
}) {
  const isUnread = !notification.read_at
  const payload = notification.payload as Record<string, string> | undefined
  const message = payload?.message || notification.type
  const Icon = iconFor(notification.type)

  return (
    <div
      className={`flex items-start justify-between gap-4 rounded-card border p-4 transition-colors ${
        isUnread ? 'border-accent/20 bg-accent-subtle/40' : 'border-border bg-bg-surface'
      }`}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${
            isUnread ? 'bg-accent-subtle text-accent' : 'bg-bg-raised text-text-muted'
          } [&_svg]:h-[18px] [&_svg]:w-[18px]`}
        >
          <Icon />
        </span>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {isUnread && <span className="h-2 w-2 shrink-0 rounded-full bg-accent" />}
            <span className="font-medium text-text-primary">{message}</span>
          </div>
          <div className="mt-0.5 text-sm text-text-muted">
            {formatRelative(notification.created_at)}
          </div>
        </div>
      </div>
      {isUnread && (
        <Button
          variant="ghost"
          size="sm"
          loading={pending}
          onClick={() => onMarkRead(notification.id)}
        >
          Mark as read
        </Button>
      )}
    </div>
  )
}

export function NotificationsPage() {
  const { data: notifications, isLoading } = useNotifications()
  const markRead = useMarkNotificationRead()

  const unread = useMemo(
    () => (notifications ?? []).filter((n) => !n.read_at),
    [notifications],
  )

  const markAllRead = () => {
    for (const n of unread) markRead.mutate(n.id)
  }

  const unreadLabel =
    unread.length === 0
      ? 'You are all caught up'
      : `${unread.length} unread notification${unread.length === 1 ? '' : 's'}`

  return (
    <div className="max-w-3xl flex flex-col gap-6">
      <PageHeader
        eyebrow="SYSTEM"
        icon={<Bell />}
        title="Notifications"
        description="Stay updated on important events in your workspace."
        actions={
          unread.length > 0 ? (
            <Button variant="secondary" size="sm" loading={markRead.isPending} onClick={markAllRead}>
              <CheckCheck />
              Mark all as read
            </Button>
          ) : undefined
        }
      />

      {!isLoading && (
        <p className="text-sm text-text-secondary">{unreadLabel}</p>
      )}

      {isLoading ? (
        <div className="flex flex-col gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-[76px] rounded-card" />
          ))}
        </div>
      ) : (notifications?.length ?? 0) === 0 ? (
        <EmptyState
          icon={<Bell />}
          title="No notifications yet"
          description="When something happens in your workspace, it will show up here."
        />
      ) : (
        <div className="flex flex-col gap-3 animate-fade-in-up">
          {notifications?.map((n) => (
            <NotificationItem
              key={n.id}
              notification={n}
              onMarkRead={markRead.mutate}
              pending={markRead.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}
