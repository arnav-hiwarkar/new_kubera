import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users,
  Wallet,
  TrendingUp,
  Trophy,
  Archive,
  ShieldCheck,
  Target,
  Laptop,
  ClipboardCheck,
  ArrowUpRight,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { salesApi } from '@/api/endpoints/sales'
import { usersApi } from '@/api/endpoints/users'
import { Card, StatCard, StatusBadge } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { humanize } from '@/api/enums'
import { formatMoney } from '@/lib/format'
import { cn } from '@/lib/cn'

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

const quickLinks = [
  { label: 'DocVault', to: '/app/docvault', icon: Archive, desc: 'Documents & versions' },
  { label: 'AuditEase', to: '/app/auditease', icon: ShieldCheck, desc: 'Audit engagements' },
  { label: 'KRA & Appraisals', to: '/app/kra', icon: Target, desc: 'Goals & reviews' },
  { label: 'Assets', to: '/app/assets', icon: Laptop, desc: 'Company assets' },
  { label: 'Sales', to: '/app/sales', icon: TrendingUp, desc: 'Pipeline & deals' },
  { label: 'ROC Compliance', to: '/app/compliance/roc', icon: ClipboardCheck, desc: 'Statutory filings' },
]

export function Dashboard() {
  const navigate = useNavigate()
  const { profile } = useCompanyAuth()
  const sales = useQuery({ queryKey: ['sales', 'aggregate'], queryFn: () => salesApi.aggregate() })
  const users = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list() })

  const firstName = (profile?.full_name ?? profile?.email ?? 'there').split(' ')[0].split('@')[0]
  const today = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })

  const rows = sales.data ?? []
  const stats = useMemo(() => {
    const totalValue = rows.reduce((s, r) => s + r.total_amount, 0)
    const totalDeals = rows.reduce((s, r) => s + r.count, 0)
    const wonRow = rows.find((r) => /won|closed/i.test(r.status))
    const maxAmount = Math.max(1, ...rows.map((r) => r.total_amount))
    return { totalValue, totalDeals, wonRow, maxAmount }
  }, [rows])

  return (
    <div className="flex flex-col gap-6">
      {/* Greeting */}
      <div>
        <p className="text-sm font-medium text-accent">{today}</p>
        <h1 className="mt-1 text-3xl font-bold tracking-display text-text-primary">
          {greeting()}, {firstName} 👋
        </h1>
        <p className="mt-1.5 text-base text-text-secondary">
          Here’s what’s happening across your workspace today.
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Team members"
          value={users.data?.length ?? 0}
          icon={<Users />}
          tone="accent"
          loading={users.isLoading}
          sub="Active directory"
        />
        <StatCard
          label="Pipeline value"
          value={stats.totalValue}
          prefix="₹"
          icon={<Wallet />}
          tone="gold"
          loading={sales.isLoading}
          sub={`${rows.length} stage${rows.length === 1 ? '' : 's'}`}
        />
        <StatCard
          label="Total deals"
          value={stats.totalDeals}
          icon={<TrendingUp />}
          tone="info"
          loading={sales.isLoading}
          sub="Across all stages"
        />
        <StatCard
          label="Won value"
          value={stats.wonRow?.total_amount ?? 0}
          prefix="₹"
          icon={<Trophy />}
          tone="accent"
          loading={sales.isLoading}
          sub={stats.wonRow ? humanize(stats.wonRow.status) : 'No closed deals yet'}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Pipeline breakdown */}
        <Card className="lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-md font-semibold text-text-primary">Sales pipeline</h2>
              <p className="text-sm text-text-muted">Value distribution by stage</p>
            </div>
            <button
              onClick={() => navigate('/app/sales')}
              className="flex items-center gap-1 text-sm font-medium text-accent hover:underline"
            >
              View all <ArrowUpRight className="h-3.5 w-3.5" />
            </button>
          </div>
          {sales.isLoading ? (
            <div className="flex flex-col gap-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-10 rounded-lg" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-muted">No sales data yet.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {rows.map((r, i) => (
                <div key={r.status} className="flex items-center gap-3">
                  <div className="w-32 shrink-0">
                    <StatusBadge status={r.status} />
                  </div>
                  <div className="relative h-8 flex-1 overflow-hidden rounded-lg bg-bg-inset">
                    <div
                      className="absolute inset-y-0 left-0 rounded-lg bg-accent-gradient opacity-90"
                      style={{
                        width: `${Math.max(4, (r.total_amount / stats.maxAmount) * 100)}%`,
                        animation: `fade-in-up 0.5s ${i * 0.06}s both`,
                      }}
                    />
                    <div className="absolute inset-0 flex items-center justify-between px-3">
                      <span className="font-mono text-xs font-medium text-white mix-blend-plus-lighter">
                        ₹{formatMoney(r.total_amount)}
                      </span>
                      <span className="font-mono text-xs text-text-secondary">{r.count} deals</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Quick launch */}
        <Card>
          <h2 className="mb-4 text-md font-semibold text-text-primary">Jump back in</h2>
          <div className="grid grid-cols-2 gap-2.5">
            {quickLinks.map((q) => (
              <button
                key={q.to}
                onClick={() => navigate(q.to)}
                className={cn(
                  'group flex flex-col items-start gap-2 rounded-lg border border-border bg-bg-surface p-3 text-left transition-all duration-200 ease-spring',
                  'hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-card',
                )}
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-subtle text-accent transition-colors group-hover:bg-accent group-hover:text-white">
                  <q.icon className="h-4 w-4" />
                </span>
                <span className="text-sm font-semibold text-text-primary">{q.label}</span>
                <span className="text-xs text-text-muted">{q.desc}</span>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
