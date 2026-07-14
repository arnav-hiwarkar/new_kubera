import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ClipboardCheck,
  BookOpen,
  Network,
  FileText,
  ListChecks,
  MessagesSquare,
  FileBarChart,
  Users,
  Layers,
  Scale,
  ScrollText,
} from 'lucide-react'
import {
  Button,
  Card,
  StatCard,
  StatusBadge,
  Spinner,
  EmptyState,
  ConfirmDialog,
  Tabs,
  useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import { formatMoney } from '@/lib/format'
import { useEngagement, useCompanyTrialBalance, useCloseEngagement } from '@/api/hooks/auditease'
import { TrialBalanceTable } from '@/components/auditease/TrialBalanceTable'
import { ImportTrialBalanceModal } from './ImportTrialBalanceModal'
import { InviteAuditorModal } from './InviteAuditorModal'
import { MappingTab } from './MappingTab'
import { RequirementsTab } from './RequirementsTab'
import { QueriesTab } from './QueriesTab'
import { AuditEntriesTab } from './AuditEntriesTab'
import { ReportsTab } from './ReportsTab'
import { useListRequirements, useListQueries, useListEntries } from '@/api/hooks/auditease'

type Tab = 'overview' | 'trial-balance' | 'mapping' | 'entries' | 'requirements' | 'queries' | 'reports'

export function EngagementWorkspace() {
  const { engagementId = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const { data: eng, isLoading } = useEngagement(engagementId)
  const { data: accounts = [], isLoading: tbLoading } = useCompanyTrialBalance(engagementId)
  const closeEng = useCloseEngagement()

  const { data: reqs = [] } = useListRequirements(engagementId)
  const { data: queries = [] } = useListQueries(engagementId)
  const { data: entries = [] } = useListEntries(engagementId)

  const [tab, setTab] = useState<Tab>('overview')
  const [importOpen, setImportOpen] = useState(false)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [closeOpen, setCloseOpen] = useState(false)

  if (isLoading) return <Spinner className="mx-auto mt-16 h-6 w-6" />
  if (!eng)
    return (
      <EmptyState title="Engagement not found" description="It may have been deleted or closed." />
    )

  const totalDebit = accounts.reduce((s, a) => s + a.debit, 0)
  const totalCredit = accounts.reduce((s, a) => s + a.credit, 0)
  const balanced = Math.round((totalDebit - totalCredit) * 100) === 0
  const closed = eng.status === 'closed'

  const doClose = async () => {
    try {
      await closeEng.mutateAsync(eng.id)
      toast.success('Engagement closed')
      setCloseOpen(false)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not close')
    }
  }

  const mappedCount = accounts.filter((a) => a.mapped_group_id).length
  const mappedRatio = accounts.length > 0 ? Math.round((mappedCount / accounts.length) * 100) : 0

  const tabs = [
    { id: 'overview', label: 'Overview', icon: <ClipboardCheck /> },
    { id: 'trial-balance', label: 'Trial Balance', icon: <BookOpen /> },
    { id: 'mapping', label: 'Chart of Accounts', icon: <Network /> },
    { id: 'entries', label: 'Entries', icon: <FileText />, count: entries.filter((e) => e.status === 'proposed').length },
    { id: 'requirements', label: 'Requirements', icon: <ListChecks />, count: reqs.filter((r) => r.status === 'open').length },
    { id: 'queries', label: 'Queries', icon: <MessagesSquare />, count: queries.filter((q) => q.status === 'open').length },
    { id: 'reports', label: 'Reports', icon: <FileBarChart /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 mb-2 text-text-muted"
          onClick={() => navigate('/app/auditease')}
        >
          <ArrowLeft className="h-4 w-4" /> All engagements
        </Button>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-subtle text-accent [&_svg]:h-5 [&_svg]:w-5">
              <ClipboardCheck />
            </span>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-[0.08em] text-accent">ENGAGEMENT</p>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold tracking-display text-text-primary">{eng.period_label}</h1>
                <StatusBadge status={eng.status} />
              </div>
            </div>
          </div>
          {!closed && (
            <div className="flex shrink-0 gap-2">
              <Button variant="secondary" onClick={() => setInviteOpen(true)}>
                {eng.auditor_email ? 'Change auditor' : 'Invite auditor'}
              </Button>
              {(eng.status === 'invited' || eng.status === 'active') && (
                <Button variant="secondary" onClick={() => setCloseOpen(true)}>
                  Close
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <Tabs
        tabs={tabs}
        value={tab}
        onChange={(id) => setTab(id as Tab)}
        accent="company"
        layoutGroup="company-workspace"
      />

      {/* Overview */}
      {tab === 'overview' && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-text-secondary">Status</p>
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent-subtle text-accent [&_svg]:h-[18px] [&_svg]:w-[18px]">
                <ClipboardCheck />
              </span>
            </div>
            <div className="mt-3"><StatusBadge status={eng.status} /></div>
            <p className="mt-1 truncate text-sm text-text-muted">{eng.auditor_email ?? 'No auditor invited'}</p>
          </Card>
          <StatCard label="Ledgers" value={accounts.length} icon={<Layers />} tone="info" loading={tbLoading} />
          <StatCard
            label="Mapped"
            value={mappedRatio}
            suffix="%"
            icon={<Network />}
            tone="accent"
            loading={tbLoading}
            sub={`${mappedCount} of ${accounts.length} ledgers`}
          />
          <StatCard
            label="Balanced"
            display={
              <span
                className={
                  accounts.length === 0
                    ? 'text-text-muted'
                    : balanced
                      ? 'text-status-verified'
                      : 'text-status-pending'
                }
              >
                {accounts.length === 0 ? '—' : balanced ? 'Yes' : 'No'}
              </span>
            }
            icon={<Scale />}
            tone={accounts.length === 0 ? 'neutral' : balanced ? 'accent' : 'warning'}
            sub={
              accounts.length > 0 && !balanced
                ? `Dr ${formatMoney(totalDebit)} / Cr ${formatMoney(totalCredit)}`
                : undefined
            }
          />
          <StatCard
            label="Open requirements"
            value={reqs.filter((r) => r.status === 'open').length}
            icon={<ListChecks />}
            tone="info"
          />
          <StatCard
            label="Open queries"
            value={queries.filter((q) => q.status === 'open').length}
            icon={<MessagesSquare />}
            tone="info"
          />
          <StatCard
            label="Pending entries"
            value={entries.filter((e) => e.status === 'proposed').length}
            icon={<ScrollText />}
            tone="warning"
          />
          <StatCard
            label="Auditor"
            display={<span className="truncate text-lg">{eng.auditor_email ? eng.auditor_email.split('@')[0] : 'None'}</span>}
            icon={<Users />}
            tone="neutral"
            sub={eng.auditor_grant_status ?? (eng.auditor_email ? undefined : 'Not invited')}
          />
        </div>
      )}

      {/* Trial Balance */}
      {tab === 'trial-balance' && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-text-secondary">
              {accounts.length > 0
                ? `${accounts.length} ledgers imported.`
                : 'No trial balance imported yet.'}
            </p>
            {!closed && (
              <Button onClick={() => setImportOpen(true)}>
                {accounts.length > 0 ? 'Re-import' : 'Import trial balance'}
              </Button>
            )}
          </div>
          <TrialBalanceTable accounts={accounts} loading={tbLoading} />
        </div>
      )}

      {/* Mapping */}
      {tab === 'mapping' && <MappingTab engagementId={eng.id} />}

      {tab === 'requirements' && <RequirementsTab engagementId={eng.id} />}
      {tab === 'queries' && <QueriesTab engagementId={eng.id} />}
      {tab === 'entries' && <AuditEntriesTab engagementId={eng.id} />}
      {tab === 'reports' && <ReportsTab engagementId={eng.id} />}

      {importOpen && (
        <ImportTrialBalanceModal
          open
          onClose={() => setImportOpen(false)}
          engagementId={eng.id}
        />
      )}
      {inviteOpen && (
        <InviteAuditorModal
          open
          onClose={() => setInviteOpen(false)}
          engagementId={eng.id}
          currentEmail={eng.auditor_email}
        />
      )}
      <ConfirmDialog
        open={closeOpen}
        title="Close engagement?"
        message="Closing revokes the auditor's access. Data and reports are retained. This cannot be reopened."
        confirmLabel="Close engagement"
        loading={closeEng.isPending}
        onConfirm={doClose}
        onCancel={() => setCloseOpen(false)}
      />
    </div>
  )
}
