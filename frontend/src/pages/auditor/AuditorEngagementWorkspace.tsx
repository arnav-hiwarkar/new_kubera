import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Card, StatusBadge, Spinner, EmptyState } from '@/components/ui'
import { cn } from '@/lib/cn'
import { formatMoney } from '@/lib/format'
import { useAuditorEngagements, useAuditorTrialBalance } from '@/api/hooks/auditorEngagements'
import { TrialBalanceTable } from '@/components/auditease/TrialBalanceTable'
import { RequirementsTab } from './RequirementsTab'
import { QueriesTab } from './QueriesTab'
import { AuditorEntriesTab } from './AuditorEntriesTab'
import { useAuditorListRequirements, useAuditorListQueries, useAuditorListEntries } from '@/api/hooks/auditorEngagements'

type Tab = 'overview' | 'trial-balance' | 'entries' | 'requirements' | 'queries'

export function AuditorEngagementWorkspace() {
  const { engagementId = '' } = useParams()
  const navigate = useNavigate()

  const { data: engagements = [], isLoading } = useAuditorEngagements()
  const { data: accounts = [], isLoading: tbLoading } = useAuditorTrialBalance(engagementId)
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

  const totalDebit = accounts.reduce((s, a) => s + a.debit, 0)
  const totalCredit = accounts.reduce((s, a) => s + a.credit, 0)
  const balanced = Math.round((totalDebit - totalCredit) * 100) === 0

  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'trial-balance', label: 'Trial Balance' },
    { id: 'entries', label: 'Entries' },
    { id: 'requirements', label: 'Requirements' },
    { id: 'queries', label: 'Queries' },
  ]

  return (
    <div>
      <div className="mb-5">
        <button
          onClick={() => navigate('/auditor/app')}
          className="mb-2 text-sm text-text-muted hover:text-text-primary"
        >
          ← All engagements
        </button>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-text-primary">{eng.period_label}</h1>
          <StatusBadge status={eng.status} />
        </div>
      </div>

      <div className="mb-4 flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === t.id
                ? 'border-accent text-text-primary'
                : 'border-transparent text-text-muted hover:text-text-primary',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <div className="text-sm text-text-muted">Status</div>
            <div className="mt-1"><StatusBadge status={eng.status} /></div>
          </Card>
          <Card>
            <div className="text-sm text-text-muted">Ledgers</div>
            <div className="mt-1 text-2xl font-semibold text-text-primary">{accounts.length}</div>
          </Card>
          <Card>
            <div className="text-sm text-text-muted">Balanced</div>
            <div
              className={cn(
                'mt-1 text-base font-medium',
                accounts.length === 0
                  ? 'text-text-muted'
                  : balanced
                    ? 'text-status-verified'
                    : 'text-status-pending',
              )}
            >
              {accounts.length === 0
                ? '—'
                : balanced
                  ? 'Yes'
                  : `No · Dr ${formatMoney(totalDebit)} / Cr ${formatMoney(totalCredit)}`}
            </div>
          </Card>
          <Card>
            <div className="text-sm text-text-muted">Requirements</div>
            <div className="mt-1 text-2xl font-semibold text-text-primary">
              {reqs.filter(r => r.status === 'open').length} <span className="text-base font-normal text-text-muted">open</span>
            </div>
          </Card>
          <Card>
            <div className="text-sm text-text-muted">Queries</div>
            <div className="mt-1 text-2xl font-semibold text-text-primary">
              {queries.filter(q => q.status === 'open').length} <span className="text-base font-normal text-text-muted">open</span>
            </div>
          </Card>
          <Card>
            <div className="text-sm text-text-muted">Entries</div>
            <div className="mt-1 text-2xl font-semibold text-text-primary">
              {entries.length} <span className="text-base font-normal text-text-muted">total</span>
            </div>
          </Card>
        </div>
      )}

      {tab === 'trial-balance' && <TrialBalanceTable accounts={accounts} loading={tbLoading} readonly={true} />}
      {tab === 'entries' && <AuditorEntriesTab engagementId={eng.id} />}
      {tab === 'requirements' && <RequirementsTab engagementId={eng.id} />}
      {tab === 'queries' && <QueriesTab engagementId={eng.id} />}
    </div>
  )
}
