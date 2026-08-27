import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ClipboardCheck,
  BookOpen,
  FileText,
  ListChecks,
  MessagesSquare,
  ScrollText,
} from 'lucide-react'
import { Button, Card, StatCard, StatusBadge, Spinner, EmptyState, Tabs } from '@/components/ui'
import { useAuditorEngagements, useAuditorTrialBalance } from '@/api/hooks/auditorEngagements'
import { TrialBalanceTable } from '@/components/auditease/TrialBalanceTable'
import { BalanceStatCards } from '@/components/auditease/BalanceStatCards'
import { TrialBalanceLoadError } from '@/components/auditease/TrialBalanceLoadError'
import { RequirementsTab } from './RequirementsTab'
import { QueriesTab } from './QueriesTab'
import { AuditorEntriesTab } from './AuditorEntriesTab'
import { useAuditorListRequirements, useAuditorListQueries, useAuditorListEntries } from '@/api/hooks/auditorEngagements'

type Tab = 'overview' | 'trial-balance' | 'entries' | 'requirements' | 'queries'

export function AuditorEngagementWorkspace() {
  const { engagementId = '' } = useParams()
  const navigate = useNavigate()

  const { data: engagements = [], isLoading } = useAuditorEngagements()
  const {
    data: tbView,
    isLoading: tbLoading,
    isError: tbIsError,
    error: tbError,
    refetch: refetchTrialBalance,
  } = useAuditorTrialBalance(engagementId)
  const { data: reqs = [] } = useAuditorListRequirements(engagementId)
  const { data: queries = [] } = useAuditorListQueries(engagementId)
  const { data: entries = [] } = useAuditorListEntries(engagementId)
  const eng = engagements.find((e) => e.id === engagementId)

  const [tab, setTab] = useState<Tab>('overview')

  if (isLoading) return <Spinner className="mx-auto mt-16 h-6 w-6" />
  if (!eng)
    return (
      <EmptyState
        title="Engagement unavailable"
        description="You may not have access, or it has been closed."
      />
    )

  const perms = eng.area_permissions ?? {}
  const baseTabs = [
    { id: 'overview', label: 'Overview', icon: <ClipboardCheck />, area: undefined },
    { id: 'trial-balance', label: 'Trial Balance', icon: <BookOpen />, area: 'trial_balance' },
    { id: 'entries', label: 'Entries', icon: <FileText />, area: 'entries', count: entries.length },
    { id: 'requirements', label: 'Requirements', icon: <ListChecks />, area: 'requirements', count: reqs.filter((r) => r.status === 'open').length },
    { id: 'queries', label: 'Queries', icon: <MessagesSquare />, area: 'queries', count: queries.filter((q) => q.status === 'open').length },
  ]
  const tabs = baseTabs.filter((t) => !t.area || perms[t.area] !== false)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button
          variant="ghost"
          size="sm"
          className="-ml-2 mb-2 text-text-muted"
          onClick={() => navigate('/auditor/app')}
        >
          <ArrowLeft className="h-4 w-4" /> All engagements
        </Button>
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-auditor-subtle text-auditor [&_svg]:h-5 [&_svg]:w-5">
            <ClipboardCheck />
          </span>
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-[0.08em] text-auditor">ENGAGEMENT</p>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-display text-text-primary">{eng.period_label}</h1>
              <StatusBadge status={eng.status} />
            </div>
          </div>
        </div>
      </div>

      <Tabs
        tabs={tabs}
        value={tab}
        onChange={(id) => setTab(id as Tab)}
        accent="auditor"
        layoutGroup="auditor-workspace"
      />

      {tab === 'overview' && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-text-secondary">Status</p>
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-auditor-subtle text-auditor [&_svg]:h-[18px] [&_svg]:w-[18px]">
                <ClipboardCheck />
              </span>
            </div>
            <div className="mt-3"><StatusBadge status={eng.status} /></div>
          </Card>
          {tbIsError ? (
            <TrialBalanceLoadError
              error={tbError}
              onRetry={() => void refetchTrialBalance()}
              className="sm:col-span-2"
            />
          ) : (
            <BalanceStatCards totals={tbView?.totals} loading={tbLoading} accent="auditor" />
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
          <StatCard label="Entries" value={entries.length} icon={<ScrollText />} tone="neutral" />
        </div>
      )}

      {tab === 'trial-balance' && (
        tbIsError
          ? <TrialBalanceLoadError error={tbError} onRetry={() => void refetchTrialBalance()} />
          : <TrialBalanceTable view={tbView} loading={tbLoading} readonly={true} />
      )}
      {tab === 'entries' && <AuditorEntriesTab engagementId={eng.id} />}
      {tab === 'requirements' && (
        <RequirementsTab engagementId={eng.id} canQuery={perms.queries !== false} />
      )}
      {tab === 'queries' && <QueriesTab engagementId={eng.id} />}
    </div>
  )
}
