import { useQuery } from '@tanstack/react-query'
import { salesApi } from '@/api/endpoints/sales'
import { usersApi } from '@/api/endpoints/users'
import { PageHeader, Card, Spinner } from '@/components/ui'
import { humanize } from '@/api/enums'

export function Dashboard() {
  const sales = useQuery({ queryKey: ['sales', 'aggregate'], queryFn: () => salesApi.aggregate() })
  const users = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list() })

  return (
    <div>
      <PageHeader title="Dashboard" description="Overview of your company workspace" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <p className="text-sm text-text-secondary">Team members</p>
          <p className="mt-1 text-xl font-semibold text-text-primary">
            {users.isLoading ? <Spinner className="h-5 w-5" /> : (users.data?.length ?? '—')}
          </p>
        </Card>
        {sales.isLoading ? (
          <Card>
            <Spinner className="h-5 w-5" />
          </Card>
        ) : (
          (sales.data ?? []).map((row) => (
            <Card key={row.status}>
              <p className="text-sm text-text-secondary">{humanize(row.status)}</p>
              <p className="mt-1 text-xl font-semibold text-text-primary">
                {row.count}
                <span className="ml-2 font-mono text-sm font-normal text-text-muted">
                  {row.total_amount.toLocaleString()}
                </span>
              </p>
            </Card>
          ))
        )}
      </div>
    </div>
  )
}
