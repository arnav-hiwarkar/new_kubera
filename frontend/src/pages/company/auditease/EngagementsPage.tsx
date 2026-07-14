import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, Layers, Activity, Archive } from 'lucide-react'
import {
  PageHeader,
  Button,
  DataTable,
  StatusBadge,
  StatCard,
  Modal,
  Field,
  Input,
  ConfirmDialog,
  useToast,
  type Column,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import { formatDate } from '@/lib/format'
import type { AuditEngagementResponse } from '@/api/types'
import {
  useEngagements,
  useCreateEngagement,
  useCloseEngagement,
  useDeleteEngagement,
} from '@/api/hooks/auditease'
import { InviteAuditorModal } from './InviteAuditorModal'

export function EngagementsPage() {
  const toast = useToast()
  const navigate = useNavigate()
  const { data: engagements = [], isLoading } = useEngagements()
  const createEng = useCreateEngagement()
  const closeEng = useCloseEngagement()
  const deleteEng = useDeleteEngagement()

  const [createOpen, setCreateOpen] = useState(false)
  const [period, setPeriod] = useState('')
  const [inviteFor, setInviteFor] = useState<AuditEngagementResponse | null>(null)
  const [closeFor, setCloseFor] = useState<AuditEngagementResponse | null>(null)
  const [deleteFor, setDeleteFor] = useState<AuditEngagementResponse | null>(null)
  const [confirmText, setConfirmText] = useState('')

  const create = async () => {
    const label = period.trim()
    if (!label) return
    try {
      const eng = await createEng.mutateAsync({ period_label: label })
      toast.success('Engagement created')
      setCreateOpen(false)
      setPeriod('')
      navigate(`/app/auditease/${eng.id}`)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not create engagement')
    }
  }

  const doClose = async () => {
    if (!closeFor) return
    try {
      await closeEng.mutateAsync(closeFor.id)
      toast.success('Engagement closed')
      setCloseFor(null)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not close')
    }
  }

  const doDelete = async () => {
    if (!deleteFor) return
    try {
      await deleteEng.mutateAsync(deleteFor.id)
      toast.success('Engagement deleted')
      setDeleteFor(null)
      setConfirmText('')
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not delete')
    }
  }

  const stop = (e: React.MouseEvent) => e.stopPropagation()

  const columns: Column<AuditEngagementResponse>[] = [
    {
      key: 'period_label',
      header: 'Engagement',
      sortValue: (e) => e.period_label.toLowerCase(),
      cell: (e) => <span className="font-medium text-text-primary">{e.period_label}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      sortValue: (e) => e.status,
      cell: (e) => <StatusBadge status={e.status} />,
    },
    {
      key: 'auditor',
      header: 'Auditor',
      cell: (e) =>
        e.auditor_email ? (
          <span className="flex items-center gap-2">
            <span className="text-text-secondary">{e.auditor_email}</span>
            {e.auditor_grant_status && (
              <StatusBadge
                status={e.auditor_grant_status}
                tone={
                  e.auditor_grant_status === 'accepted'
                    ? 'success'
                    : e.auditor_grant_status === 'pending'
                      ? 'info'
                      : 'warning'
                }
              />
            )}
          </span>
        ) : (
          <span className="text-text-muted">—</span>
        ),
    },
    {
      key: 'created_at',
      header: 'Created',
      sortValue: (e) => e.created_at,
      cell: (e) => <span className="text-text-muted">{formatDate(e.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      cell: (e) => (
        <div className="flex justify-end gap-1" onClick={stop}>
          {e.status !== 'closed' && (
            <Button size="sm" variant="ghost" onClick={() => setInviteFor(e)}>
              Invite
            </Button>
          )}
          {(e.status === 'invited' || e.status === 'active') && (
            <Button size="sm" variant="ghost" onClick={() => setCloseFor(e)}>
              Close
            </Button>
          )}
          {e.status !== 'active' && (
            <Button
              size="sm"
              variant="ghost"
              className="text-status-action"
              onClick={() => {
                setDeleteFor(e)
                setConfirmText('')
              }}
            >
              Delete
            </Button>
          )}
        </div>
      ),
    },
  ]

  const deleteNeedsTyping = deleteFor?.status === 'closed'

  const totalCount = engagements.length
  const activeCount = engagements.filter((e) => e.status !== 'closed').length
  const closedCount = engagements.filter((e) => e.status === 'closed').length

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="AUDIT"
        icon={<ShieldCheck />}
        title="AuditEase"
        description="Create audit engagements, import trial balances, and collaborate with auditors."
        actions={<Button onClick={() => setCreateOpen(true)}>New engagement</Button>}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Total engagements" value={totalCount} icon={<Layers />} tone="accent" loading={isLoading} />
        <StatCard label="Active" value={activeCount} icon={<Activity />} tone="info" loading={isLoading} />
        <StatCard label="Closed" value={closedCount} icon={<Archive />} tone="neutral" loading={isLoading} />
      </div>

      <DataTable
        columns={columns}
        data={engagements}
        rowKey={(e) => e.id}
        loading={isLoading}
        onRowClick={(e) => navigate(`/app/auditease/${e.id}`)}
        searchAccessors={(e) => `${e.period_label} ${e.auditor_email ?? ''}`}
        searchPlaceholder="Search engagements…"
        emptyTitle="No engagements yet"
        emptyDescription="Create your first engagement to import a trial balance and invite an auditor."
      />

      {/* Create */}
      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New engagement"
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={create} loading={createEng.isPending} disabled={!period.trim()}>
              Create
            </Button>
          </>
        }
      >
        <Field label="Period label" required hint="e.g. FY 2024-25">
          <Input
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            placeholder="FY 2024-25"
            onKeyDown={(e) => e.key === 'Enter' && create()}
            autoFocus
          />
        </Field>
      </Modal>

      {/* Invite */}
      {inviteFor && (
        <InviteAuditorModal
          open
          onClose={() => setInviteFor(null)}
          engagementId={inviteFor.id}
          currentEmail={inviteFor.auditor_email}
        />
      )}

      {/* Close */}
      <ConfirmDialog
        open={!!closeFor}
        title="Close engagement?"
        message={`Closing "${closeFor?.period_label}" revokes the auditor's access. Data and reports are retained. This cannot be reopened.`}
        confirmLabel="Close engagement"
        loading={closeEng.isPending}
        onConfirm={doClose}
        onCancel={() => setCloseFor(null)}
      />

      {/* Delete */}
      <Modal
        open={!!deleteFor}
        onClose={() => setDeleteFor(null)}
        title="Delete engagement?"
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteFor(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={deleteEng.isPending}
              disabled={deleteNeedsTyping && confirmText !== deleteFor?.period_label}
              onClick={doDelete}
            >
              Delete permanently
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3 text-sm text-text-secondary">
          <p>
            This permanently deletes <strong>{deleteFor?.period_label}</strong> and all its data
            (trial balance, mappings, entries, queries). This cannot be undone.
          </p>
          {deleteNeedsTyping && (
            <Field label={`Type "${deleteFor?.period_label}" to confirm`} required>
              <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
            </Field>
          )}
        </div>
      </Modal>
    </div>
  )
}
