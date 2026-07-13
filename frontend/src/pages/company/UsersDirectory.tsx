import { useQuery } from '@tanstack/react-query'
import { usersApi } from '@/api/endpoints/users'
import { ApiError } from '@/api/http'
import type { UserResponse } from '@/api/types'
import { PageHeader, DataTable, StatusBadge, type Column } from '@/components/ui'

const columns: Column<UserResponse>[] = [
  {
    key: 'full_name',
    header: 'Name',
    sortValue: (u) => u.full_name.toLowerCase(),
    cell: (u) => (
      <div>
        <div className="font-medium text-text-primary">{u.full_name}</div>
        <div className="text-xs text-text-muted">{u.email}</div>
      </div>
    ),
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
    cell: (u) => <StatusBadge status={u.is_active ? 'active' : 'archived'} />,
  },
]

export function UsersDirectory() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list(),
  })

  return (
    <div>
      <PageHeader title="Directory" description="Company users and reporting hierarchy" />
      {error instanceof ApiError && error.status === 403 ? (
        <p className="text-sm text-text-secondary">
          You don&apos;t have permission to view the full directory (admin only).
        </p>
      ) : (
        <DataTable
          columns={columns}
          data={data ?? []}
          rowKey={(u) => u.id}
          loading={isLoading}
          searchAccessors={(u) => `${u.full_name} ${u.email} ${u.department ?? ''}`}
          searchPlaceholder="Search people…"
          emptyTitle="No users yet"
        />
      )}
    </div>
  )
}
