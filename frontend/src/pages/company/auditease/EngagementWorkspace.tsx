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
import { useCompanyAuth } from '@/auth/company'
import { useEngagement, useCompanyTrialBalance, useCloseEngagement, useSetSignConvention } from '@/api/hooks/auditease'
import { TrialBalanceTable } from '@/components/auditease/TrialBalanceTable'
import { BalanceStatCards } from '@/components/auditease/BalanceStatCards'
import { TrialBalanceLoadError } from '@/components/auditease/TrialBalanceLoadError'
import { ImportTrialBalanceModal } from './ImportTrialBalanceModal'
import { InviteAuditorModal } from './InviteAuditorModal'
import { MappingTab } from './MappingTab'
import { RequirementsTab } from './RequirementsTab'
import { QueriesTab } from './QueriesTab'
import { AuditEntriesTab } from './AuditEntriesTab'
import { ReportsTab } from './ReportsTab'
import { AuditorsTab } from './AuditorsTab'
import { useListRequirements, useListQueries, useListEntries } from '@/api/hooks/auditease'

type Tab = 'overview' | 'trial-balance' | 'mapping' | 'entries' | 'requirements' | 'queries' | 'auditors' | 'reports'

export function EngagementWorkspace() {
  const { engagementId = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { profile } = useCompanyAuth()
  const isAdmin = profile?.role === 'admin'

  const { data: eng, isLoading } = useEngagement(engagementId)
  const {
    data: tbView,
    isLoading: tbLoading,
    isError: tbIsError,
    error: tbError,
    refetch: refetchTrialBalance,
  } = useCompanyTrialBalance(engagementId)
  const accounts = tbView?.accounts ?? []
  const closeEng = useCloseEngagement()
  const setConvention = useSetSignConvention()

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

  const closed = eng.status === 'closed'
  const liveAuditors = (eng.auditors ?? []).filter(
    (a) => a.status === 'invited' || a.status === 'accepted' || a.status === 'pending',
  )
  const auditorCountLabel = liveAuditors.length === 1 ? '1 auditor' : `${liveAuditors.length} auditors`

  const doClose = async () => {
    try {
      await closeEng.mutateAsync(eng.id)
      toast.success('Engagement closed')
      setCloseOpen(false)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not close')
    }
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: <ClipboardCheck /> },
    { id: 'trial-balance', label: 'Trial Balance', icon: <BookOpen /> },
    { id: 'mapping', label: 'Chart of Accounts', icon: <Network /> },
    { id: 'entries', label: 'Entries', icon: <FileText />, count: entries.filter((e) => e.status === 'proposed').length },
    { id: 'requirements', label: 'Requirements', icon: <ListChecks />, count: reqs.filter((r) => r.status === 'open').length },
    { id: 'queries', label: 'Queries', icon: <MessagesSquare />, count: queries.filter((q) => q.status === 'open').length },
    { id: 'auditors', label: 'Auditors', icon: <Users /> },
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
              {isAdmin && (
                <Button variant="secondary" onClick={() => setInviteOpen(true)}>
                  Invite auditor
                </Button>
              )}
              {isAdmin && (eng.status === 'invited' || eng.status === 'active') && (
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
            <p className="mt-1 truncate text-sm text-text-muted">
              {liveAuditors.length > 0 ? auditorCountLabel : 'No auditor invited'}
            </p>
          </Card>
          {tbIsError ? (
            <TrialBalanceLoadError
              error={tbError}
              onRetry={() => void refetchTrialBalance()}
              className="sm:col-span-2 lg:col-span-3"
            />
          ) : (
            <BalanceStatCards totals={tbView?.totals} loading={tbLoading} />
          )}
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
            label="Auditors"
            display={<span className="truncate text-lg">{liveAuditors.length > 0 ? auditorCountLabel : 'None'}</span>}
            icon={<Users />}
            tone="neutral"
            sub={liveAuditors[0] ? `${liveAuditors[0].status}${liveAuditors.length > 1 ? ` +${liveAuditors.length - 1} more` : ''}` : 'Not invited'}
          />
        </div>
      )}

      {/* Trial Balance */}
      {tab === 'trial-balance' && (
        <div className="flex flex-col gap-4">
          {tbIsError ? (
            <TrialBalanceLoadError error={tbError} onRetry={() => void refetchTrialBalance()} />
          ) : (
            <>
          {tbView && accounts.length > 0 && (!tbView.sign_convention || tbView.sign_unresolved_count > 0) && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-status-pending/40 bg-status-pending/5 px-4 py-3 text-sm">
              <span className="text-status-pending">Confirm whether the source stores credit balances as negative or positive values.</span>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" loading={setConvention.isPending} onClick={() => setConvention.mutate({ engagementId, body: { convention: 'signed' } })}>Credits negative</Button>
                <Button size="sm" variant="secondary" loading={setConvention.isPending} onClick={() => setConvention.mutate({ engagementId, body: { convention: 'magnitude' } })}>All positive</Button>
              </div>
            </div>
          )}
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
          <TrialBalanceTable view={tbView} loading={tbLoading} />
            </>
          )}
        </div>
      )}

      {/* Mapping */}
      {tab === 'mapping' && <MappingTab engagementId={eng.id} />}

      {tab === 'requirements' && <RequirementsTab engagementId={eng.id} />}
      {tab === 'queries' && <QueriesTab engagementId={eng.id} />}
      {tab === 'entries' && <AuditEntriesTab engagementId={eng.id} />}
      {tab === 'auditors' && <AuditorsTab engagementId={eng.id} canManage={isAdmin} />}
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
