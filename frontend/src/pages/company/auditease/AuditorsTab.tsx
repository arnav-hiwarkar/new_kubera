import { Fragment, useState } from 'react'
import {
  Button,
  StatusBadge,
  Spinner,
  EmptyState,
  ConfirmDialog,
  useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import { companyClient } from '@/api/clients/company'
import { saveBlob } from '@/lib/download'
import { ChevronDown, ChevronUp, FileSpreadsheet, FileText, Pencil, UserMinus } from 'lucide-react'
import type { EngagementAuditorResponse } from '@/api/types'
import {
  useEngagementAuditors,
  useRemoveEngagementAuditor,
  useAuditorActivity,
} from '@/api/hooks/auditease'
import { EditAuditorAccessModal } from './EditAuditorAccessModal'

const AREA_LABELS: Record<string, string> = {
  trial_balance: 'Trial Balance',
  entries: 'Entries',
  requirements: 'Requirements',
  queries: 'Queries',
  documents: 'Documents',
}

const STATUS_TONES: Record<string, 'success' | 'info' | 'warning' | 'neutral'> = {
  accepted: 'success',
  invited: 'info',
  pending: 'warning',
  revoked: 'neutral',
}

function ActivityTimeline({
  engagementId,
  auditor,
}: {
  engagementId: string
  auditor: EngagementAuditorResponse
}) {
  const { data: events, isLoading } = useAuditorActivity(engagementId, auditor.auditor_id ?? null)
  if (isLoading) return <p className="p-3 text-sm text-text-secondary">Loading activity…</p>
  if (!events?.length) return <p className="p-3 text-sm text-text-secondary">No activity recorded yet.</p>
  return (
    <ul className="divide-y divide-border bg-bg-inset/30">
      {events.map((ev) => (
        <li key={ev.id} className="flex items-baseline gap-3 px-4 py-2 text-sm">
          <span className="w-44 shrink-0 tabular-nums text-text-secondary">
            {new Date(ev.created_at).toLocaleString()}
          </span>
          <span className="font-medium text-text-primary">{ev.action}</span>
          <span className="text-text-secondary">{ev.entity_type}</span>
        </li>
      ))}
    </ul>
  )
}

function AreaChips({ auditor }: { auditor: EngagementAuditorResponse }) {
  const enabled = Object.entries(auditor.area_permissions ?? {})
    .filter(([, v]) => v)
    .map(([k]) => k)
  if (enabled.length === 0) return <span className="text-xs text-text-muted">No access</span>
  return (
    <div className="flex flex-wrap gap-1">
      {enabled.map((k) => (
        <span key={k} className="rounded-md bg-bg-raised px-1.5 py-0.5 text-xs font-medium text-text-secondary">
          {AREA_LABELS[k] ?? k}
        </span>
      ))}
    </div>
  )
}

export function AuditorsTab({ engagementId, canManage }: { engagementId: string; canManage: boolean }) {
  const toast = useToast()
  const { data: auditors = [], isLoading } = useEngagementAuditors(engagementId)
  const remove = useRemoveEngagementAuditor(engagementId)

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editFor, setEditFor] = useState<EngagementAuditorResponse | null>(null)
  const [removeFor, setRemoveFor] = useState<EngagementAuditorResponse | null>(null)

  const exportActivity = async (auditor: EngagementAuditorResponse, format: 'xlsx' | 'pdf') => {
    try {
      const blob = await companyClient.get<Blob>(
        `/api/v1/auditease/engagements/${engagementId}/auditors/${auditor.auditor_id}/activity-report`,
        { query: { format }, responseType: 'blob' },
      )
      const slug = (auditor.name ?? auditor.email).replace(/[^a-zA-Z0-9]+/g, '_').replace(/^_+|_+$/g, '')
      saveBlob(blob, `auditor_activity_${slug}.${format}`)
      toast.success(`Downloaded ${format.toUpperCase()} activity report`)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : `Failed to export ${format.toUpperCase()}`)
    }
  }

  const doRemove = async () => {
    if (!removeFor?.auditor_id) return
    try {
      await remove.mutateAsync(removeFor.auditor_id)
      toast.success('Auditor removed')
      setRemoveFor(null)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Could not remove auditor')
    }
  }

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Auditors</h3>
          <p className="text-sm text-text-muted">
            Who has access to this engagement and what they can work in.
            {!canManage && ' Only managers and admins can change access.'}
          </p>
        </div>
      </div>

      {auditors.length === 0 ? (
        <EmptyState
          title="No auditors yet"
          description="Invite an auditor to give them access to this engagement."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-bg-surface">
          <table className="w-full text-left text-sm text-text-secondary">
            <thead className="bg-bg-inset text-xs font-medium uppercase tracking-wider text-text-muted">
              <tr>
                <th className="px-4 py-2">Auditor</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Areas</th>
                <th className="px-4 py-2">Accepted</th>
                <th className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {auditors.map((a) => {
                const isPending = !a.auditor_id
                const isExpanded = a.auditor_id !== null && expandedId === a.auditor_id
                return (
                  <Fragment key={a.email + (a.auditor_id ?? 'pending')}>
                    <tr className={isExpanded ? 'bg-bg-inset/30' : 'hover:bg-bg-inset/30'}>
                      <td className="px-4 py-3">
                        <div className="font-medium text-text-primary">{a.name ?? a.email}</div>
                        {isPending && (
                          <div className="text-xs text-status-pending">Invite pending registration</div>
                        )}
                        {a.name && <div className="text-xs text-text-muted">{a.email}</div>}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={a.status} tone={STATUS_TONES[a.status] ?? 'neutral'} />
                      </td>
                      <td className="px-4 py-3">
                        <AreaChips auditor={a} />
                      </td>
                      <td className="px-4 py-3 tabular-nums">
                        {a.accepted_at ? new Date(a.accepted_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-4 py-3">
                        {isPending ? (
                          <span className="text-xs text-text-muted">—</span>
                        ) : (
                          <div className="flex flex-wrap items-center justify-end gap-1.5">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setExpandedId(isExpanded ? null : a.auditor_id!)}
                              aria-expanded={isExpanded}
                            >
                              {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                              Activity
                            </Button>
                            <Button size="sm" variant="secondary" onClick={() => void exportActivity(a, 'pdf')}>
                              <FileText className="h-3.5 w-3.5 text-rose-600" />
                              Export PDF
                            </Button>
                            <Button size="sm" variant="secondary" onClick={() => void exportActivity(a, 'xlsx')}>
                              <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-600" />
                              Export Excel
                            </Button>
                            {canManage && (
                              <>
                                <Button size="sm" variant="secondary" onClick={() => setEditFor(a)}>
                                  <Pencil className="h-3.5 w-3.5" />
                                  Edit access
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="text-status-action"
                                  onClick={() => setRemoveFor(a)}
                                >
                                  <UserMinus className="h-3.5 w-3.5" />
                                  Remove
                                </Button>
                              </>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={5} className="border-t border-border p-0">
                          <ActivityTimeline engagementId={engagementId} auditor={a} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <EditAuditorAccessModal
        open={!!editFor}
        onClose={() => setEditFor(null)}
        engagementId={engagementId}
        auditor={editFor}
      />

      <ConfirmDialog
        open={!!removeFor}
        title={`Remove ${removeFor?.name ?? removeFor?.email}?`}
        message="They immediately lose access to this engagement. Their past entries, requests and queries stay visible to your team."
        confirmLabel="Remove auditor"
        destructive
        loading={remove.isPending}
        onConfirm={doRemove}
        onCancel={() => setRemoveFor(null)}
      />
    </div>
  )
}
