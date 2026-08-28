import { useNavigate } from 'react-router-dom'
import {
  Archive,
  ShieldCheck,
  Laptop,
  ClipboardCheck,
  ScrollText,
  Clock,
  ArrowRight,
  CheckCircle2,
} from 'lucide-react'
import { Card, Button, StatusBadge } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { hasModuleAccess, type ModuleId } from '@/auth/company/modules'
import { usePendingApprovals } from '@/api/hooks/docvault'
import { formatRelative } from '@/lib/format'
import { cn } from '@/lib/cn'

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

const quickLinks: Array<{
  label: string
  to: string
  icon: typeof Archive
  desc: string
  moduleId: ModuleId
}> = [
  { label: 'DocVault', to: '/app/docvault', icon: Archive, desc: 'Documents & versions', moduleId: 'docvault' },
  { label: 'AuditEase', to: '/app/auditease', icon: ShieldCheck, desc: 'Audit engagements', moduleId: 'auditease' },
  { label: 'Assets', to: '/app/assets', icon: Laptop, desc: 'Company assets', moduleId: 'assets' },
  { label: 'ROC Compliance', to: '/app/compliance/roc', icon: ClipboardCheck, desc: 'Statutory filings', moduleId: 'roc' },
  {
    label: 'SecretarialEase',
    to: '/app/compliance/secretarial',
    icon: ScrollText,
    desc: 'Registers & meetings',
    moduleId: 'secretarial',
  },
]

export function Dashboard() {
  const navigate = useNavigate()
  const { profile } = useCompanyAuth()
  const { data: pendingApprovals = [] } = usePendingApprovals()

  const firstName = (profile?.full_name ?? profile?.email ?? 'there').split(' ')[0].split('@')[0]
  const today = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })

  const hasVaultAccess = hasModuleAccess(profile, 'docvault')

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

      {/* Pending Approvals Widget */}
      {hasVaultAccess && pendingApprovals.length > 0 && (
        <Card className="border-amber-500/30 bg-amber-500/5">
          <div className="flex items-center justify-between gap-4 mb-3">
            <div className="flex items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/20 text-amber-400">
                <Clock className="h-4 w-4" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-text-primary">
                  Documents Pending Your Approval
                </h2>
                <p className="text-xs text-text-muted">
                  You have {pendingApprovals.length} document{pendingApprovals.length === 1 ? '' : 's'} waiting for your review.
                </p>
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate('/app/docvault')}
              className="text-xs"
            >
              View all in DocVault
              <ArrowRight className="h-3.5 w-3.5 ml-1" />
            </Button>
          </div>

          <div className="flex flex-col divide-y divide-border/60 rounded-lg border border-border/80 bg-bg-surface overflow-hidden">
            {pendingApprovals.slice(0, 5).map((doc) => (
              <div
                key={doc.id}
                className="flex items-center justify-between gap-3 p-3 transition-colors hover:bg-bg-raised/60"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-bg-raised text-text-muted">
                    <Archive className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium text-sm text-text-primary">{doc.title}</span>
                      <StatusBadge status={doc.status} />
                    </div>
                    <p className="truncate text-xs text-text-muted mt-0.5">
                      Uploaded by <span className="text-text-secondary">{doc.created_by_name || 'Team member'}</span> ·{' '}
                      {formatRelative(doc.approval_requested_at || doc.created_at)}
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => navigate(`/app/docvault?doc=${doc.id}`)}
                  className="shrink-0 border-accent/40 bg-accent-subtle/30 text-accent hover:bg-accent hover:text-white text-xs font-semibold py-1 px-2.5 h-7"
                >
                  <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                  Review & Approve
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Quick launch */}
      <Card>
        <h2 className="mb-4 text-md font-semibold text-text-primary">Jump back in</h2>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
          {quickLinks.filter((q) => hasModuleAccess(profile, q.moduleId)).map((q) => (
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
  )
}
