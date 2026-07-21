import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, ShieldCheck, UserCog, User } from 'lucide-react'
import { usersApi } from '@/api/endpoints/users'
import { ApiError } from '@/api/http'
import { useCompanyAuth } from '@/auth/company'
import { cn } from '@/lib/cn'
import type { UserResponse } from '@/api/types'
import { PageHeader, DataTable, StatusBadge, StatCard, type Column, Button } from '@/components/ui'
import { UserModal } from './users/UserModal'

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

type UserState = 'active' | 'inactive' | 'deleted'

/** Derive the display status from is_active + deleted_at. */
export function userState(u: UserResponse): UserState {
  if (u.deleted_at) return 'deleted'
  return u.is_active ? 'active' : 'inactive'
}

const STATE_BADGE: Record<UserState, { label: string; tone: 'success' | 'neutral' | 'danger' }> = {
  active: { label: 'Active', tone: 'success' },
  inactive: { label: 'Inactive', tone: 'neutral' },
  deleted: { label: 'Deleted', tone: 'danger' },
}

const columns: Column<UserResponse>[] = [
  {
    key: 'full_name',
    header: 'Name',
    sortValue: (u) => u.full_name.toLowerCase(),
    cell: (u) => {
      const muted = userState(u) === 'deleted'
      return (
        <div className={cn('flex items-center gap-3', muted && 'opacity-50')}>
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-xs font-semibold text-accent">
            {initials(u.full_name)}
          </span>
          <div className="min-w-0">
            <div className="truncate font-medium text-text-primary">{u.full_name}</div>
            <div className="truncate text-xs text-text-muted">{u.email}</div>
          </div>
        </div>
      )
    },
  },
  { key: 'designation', header: 'Designation', cell: (u) => u.designation ?? '—' },
  { key: 'department', header: 'Department', cell: (u) => u.department ?? '—' },
  {
    key: 'role',
    header: 'Role',
    sortValue: (u) => u.role,
    cell: (u) => <StatusBadge status={u.role} />,
  },
  {
    key: 'is_active',
    header: 'Status',
    cell: (u) => {
      const s = STATE_BADGE[userState(u)]
      return <StatusBadge status={s.label} tone={s.tone} />
    },
  },
]

export function UsersDirectory() {
  const queryClient = useQueryClient()
  const { profile: currentUser } = useCompanyAuth()
  const isAdmin = currentUser?.role === 'admin'
  const [modalOpen, setModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list(),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['users'] })

  const createMutation = useMutation({
    mutationFn: usersApi.create,
    onSuccess: invalidate,
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => usersApi.update(id, data),
    onSuccess: invalidate,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => usersApi.remove(id),
    onSuccess: invalidate,
  })

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => usersApi.deactivate(id),
    onSuccess: invalidate,
  })

  const reactivateMutation = useMutation({
    mutationFn: (id: string) => usersApi.reactivate(id),
    onSuccess: invalidate,
  })

  const handleSave = async (data: any) => {
    if (editingUser) {
      await updateMutation.mutateAsync({ id: editingUser.id, data })
    } else {
      await createMutation.mutateAsync(data)
    }
  }

  const handleDelete = async (id: string) => {
    await deleteMutation.mutateAsync(id)
  }

  const handleDeactivate = async (id: string) => {
    await deactivateMutation.mutateAsync(id)
  }

  const handleReactivate = async (id: string) => {
    await reactivateMutation.mutateAsync(id)
  }

  const handleRowClick = (u: UserResponse) => {
    setEditingUser(u)
    setModalOpen(true)
  }

  const handleAdd = () => {
    setEditingUser(null)
    setModalOpen(true)
  }

  const users = data ?? []
  // Headline counts reflect live (non-deleted) accounts.
  const liveUsers = useMemo(() => users.filter((u) => !u.deleted_at), [users])
  const roleCounts = useMemo(() => {
    const c = { admin: 0, manager: 0, employee: 0 }
    for (const u of liveUsers) {
      if (u.role === 'admin') c.admin++
      else if (u.role === 'manager') c.manager++
      else c.employee++
    }
    return c
  }, [liveUsers])

  const isForbidden = error instanceof ApiError && error.status === 403
  const loadFailed = !!error && !isForbidden

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="WORKFORCE"
        icon={<Users />}
        title="Directory"
        description="Company users and reporting hierarchy"
        actions={
          <Button variant="primary" onClick={handleAdd}>
            Add User
          </Button>
        }
      />
      {!isForbidden && !loadFailed && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Total people" value={liveUsers.length} icon={<Users />} tone="accent" loading={isLoading} />
          <StatCard label="Admins" value={roleCounts.admin} icon={<ShieldCheck />} tone="gold" loading={isLoading} />
          <StatCard label="Managers" value={roleCounts.manager} icon={<UserCog />} tone="info" loading={isLoading} />
          <StatCard label="Employees" value={roleCounts.employee} icon={<User />} tone="neutral" loading={isLoading} />
        </div>
      )}
      {isForbidden ? (
        <p className="text-sm text-text-secondary">
          You don&apos;t have permission to view the full directory (admin only).
        </p>
      ) : loadFailed ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-status-action/40 bg-status-action/10 px-4 py-3">
          <p className="text-sm font-medium text-status-action">
            Couldn&apos;t load users. {error instanceof Error ? error.message : ''}
          </p>
          <Button variant="ghost" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={users}
          rowKey={(u) => u.id}
          loading={isLoading}
          searchAccessors={(u) => `${u.full_name} ${u.email} ${u.department ?? ''}`}
          searchPlaceholder="Search people…"
          emptyTitle="No users yet"
          onRowClick={handleRowClick}
        />
      )}

      <UserModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onSave={handleSave}
        onDelete={handleDelete}
        onDeactivate={handleDeactivate}
        onReactivate={handleReactivate}
        canManage={isAdmin && !!editingUser && editingUser.id !== currentUser?.id}
        initialData={editingUser}
      />
    </div>
  )
}
