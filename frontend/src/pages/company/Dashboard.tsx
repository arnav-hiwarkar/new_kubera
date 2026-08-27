import { useNavigate } from 'react-router-dom'
import {
  Archive,
  ShieldCheck,
  Laptop,
  ClipboardCheck,
  ScrollText,
} from 'lucide-react'
import { Card } from '@/components/ui'
import { useCompanyAuth } from '@/auth/company'
import { hasModuleAccess, type ModuleId } from '@/auth/company/modules'
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

  const firstName = (profile?.full_name ?? profile?.email ?? 'there').split(' ')[0].split('@')[0]
  const today = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })

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
