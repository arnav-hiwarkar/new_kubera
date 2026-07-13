import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Button,
  Card,
  StatusBadge,
  Spinner,
  EmptyState,
  ConfirmDialog,
  useToast,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { ApiError } from '@/api/http'
import { formatMoney } from '@/lib/format'
import { useEngagement, useCompanyTrialBalance, useCloseEngagement } from '@/api/hooks/auditease'
import { TrialBalanceTable } from '@/components/auditease/TrialBalanceTable'
import { ImportTrialBalanceModal } from './ImportTrialBalanceModal'
import { InviteAuditorModal } from './InviteAuditorModal'
import { MappingTab } from './MappingTab'

type Tab = 'overview' | 'trial-balance' | 'mapping'

export function EngagementWorkspace() {
  const { engagementId = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const { data: eng, isLoading } = useEngagement(engagementId)
  const { data: accounts = [], isLoading: tbLoading } = useCompanyTrialBalance(engagementId)
  const closeEng = useCloseEngagement()

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

  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'trial-balance', label: 'Trial Balance' },
    { id: 'mapping', label: 'Mapping' },
  ]

  return (
    <div>
      {/* Header */}
      <div className="mb-5">
        <button
          onClick={() => navigate('/app/auditease')}
          className="mb-2 text-sm text-text-muted hover:text-text-primary"
        >
          ← All engagements
        </button>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-text-primary">{eng.period_label}</h1>
            <StatusBadge status={eng.status} />
          </div>
          {!closed && (
            <div className="flex gap-2">
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

      {/* Overview */}
      {tab === 'overview' && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <div className="text-sm text-text-muted">Status</div>
            <div className="mt-1"><StatusBadge status={eng.status} /></div>
          </Card>
          <Card>
            <div className="text-sm text-text-muted">Auditor</div>
            <div className="mt-1 truncate text-base font-medium text-text-primary">
              {eng.auditor_email ?? 'Not invited'}
            </div>
            {eng.auditor_grant_status && (
              <div className="mt-1 text-xs text-text-secondary">{eng.auditor_grant_status}</div>
            )}
          </Card>
          <Card>
            <div className="text-sm text-text-muted">Ledgers</div>
            <div className="mt-1 text-2xl font-semibold text-text-primary">{accounts.length}</div>
          </Card>
          <Card>
            <div className="text-sm text-text-muted">Mapped</div>
            <div className="mt-1 text-2xl font-semibold text-text-primary">
              {mappedCount}
              <span className="text-base font-normal text-text-muted">/{accounts.length}</span>
            </div>
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
