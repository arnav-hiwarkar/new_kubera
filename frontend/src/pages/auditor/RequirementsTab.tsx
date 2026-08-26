import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ChevronRight,
  Download,
  History,
  MessageSquarePlus,
  Plus,
  Trash2,
  Upload,
} from 'lucide-react'
import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Input,
  Spinner,
  StatusBadge,
  useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import {
  useAuditorCreateQuery,
  useAuditorDeleteRequirement,
  useAuditorListRequirements,
  useAuditorReviewRequirement,
} from '@/api/hooks/auditorEngagements'
import { auditorEngagementsApi } from '@/api/endpoints/auditorEngagements'
import type { RequirementRequestResponse } from '@/api/types'
import { saveBlob } from '@/lib/download'
import {
  RequirementsProgress,
  type RequestStatusFilter,
} from '@/components/auditease/requirements/RequirementsProgress'
import { PriorityChip } from '@/components/auditease/requirements/PriorityChip'
import { NewRequirementModal } from '@/components/auditease/requirements/NewRequirementModal'
import { BulkImportModal } from '@/components/auditease/requirements/BulkImportModal'

type Req = RequirementRequestResponse

function isOverdue(iso: string | null | undefined): boolean {
  if (!iso) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return new Date(`${iso.slice(0, 10)}T00:00:00`) < today
}

function fmtDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function RequirementsTab({
  engagementId,
  canQuery,
}: {
  engagementId: string
  canQuery: boolean
}) {
  const toast = useToast()
  const { data: reqs = [], isLoading } = useAuditorListRequirements(engagementId)
  const review = useAuditorReviewRequirement()
  const del = useAuditorDeleteRequirement()
  const createQuery = useAuditorCreateQuery()

  const [filter, setFilter] = useState<RequestStatusFilter | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [expandedChildren, setExpandedChildren] = useState<Record<string, boolean>>({})
  const [historyFor, setHistoryFor] = useState<string | null>(null)
  const [clarifyFor, setClarifyFor] = useState<string | null>(null)
  const [clarifyNote, setClarifyNote] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Req | null>(null)

  const roots = useMemo(() => reqs.filter((r) => !r.parent_requirement_id), [reqs])
  const childrenOf = (id: string) =>
    reqs.filter((r) => r.parent_requirement_id === id).sort((a, b) => (a.seq_number ?? 0) - (b.seq_number ?? 0))

  const visibleRoots = (filter ? reqs.filter((r) => r.status === filter) : reqs).filter(
    (r) => !r.parent_requirement_id,
  )
  const visibleChildrenOf = (id: string) =>
    visibleRootFilter(childrenOf(id), filter)

  const nextReqId = `REQ-${String(Math.max(0, ...reqs.map((r) => r.seq_number ?? 0)) + 1).padStart(3, '0')}`

  const handleDownload = async (docId: string) => {
    try {
      const doc = await auditorEngagementsApi.getDocument(docId)
      const blob = await auditorEngagementsApi.downloadDocument(docId)
      const version = doc.versions.find((v) => v.id === doc.current_version_id)
      saveBlob(blob, version?.original_filename || 'document')
    } catch {
      toast.error('Failed to download document')
    }
  }

  const handleReview = async (req: Req, action: 'accept' | 'clarify', note?: string) => {
    try {
      await review.mutateAsync({ engagementId, reqId: req.id, body: { action, note } })
      toast.success(
        action === 'accept'
          ? `${req.requirement_id_str ?? 'Requirement'} accepted`
          : `${req.requirement_id_str ?? 'Requirement'} marked for clarification`,
      )
      setClarifyFor(null)
      setClarifyNote('')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error')
    }
  }

  const handleInitiateQuery = async (req: Req) => {
    try {
      const fd = new FormData()
      fd.append('initial_message', `Clarification on ${req.requirement_id_str}: ${req.description}\n\n`)
      fd.append('requirement_id', req.id)
      await createQuery.mutateAsync({ engagementId, formData: fd })
      toast.success(`Query opened for ${req.requirement_id_str}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not open query')
    }
  }

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  return (
    <div className="flex flex-col gap-6">
      <RequirementsProgress requirements={reqs} activeFilter={filter} onFilterChange={setFilter} />

      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-medium text-text-primary">Requested documents</h3>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setShowImport(true)}>
            <Upload className="h-4 w-4" /> Bulk import
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" /> New requirement
          </Button>
        </div>
      </div>

      {roots.length === 0 ? (
        <EmptyState
          title="No requirements"
          description="Request documents or import your requirement list."
        />
      ) : visibleRoots.length === 0 ? (
        <EmptyState
          title={`No ${filter?.replace('_', ' ')} requirements`}
          description="Try another status filter."
        />
      ) : (
        <AnimatePresence initial={false}>
          {visibleRoots.map((req) => {
            const kids = visibleChildrenOf(req.id)
            const allKids = childrenOf(req.id)
            const open = expandedChildren[req.id] ?? false
            return (
              <motion.div
                key={req.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="flex flex-col gap-2"
              >
                <Card className="flex flex-col gap-3 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-bg-raised px-1.5 py-0.5 font-mono text-xs text-text-secondary">
                      {req.requirement_id_str}
                    </span>
                    <StatusBadge status={req.status} />
                    {(req.priority ?? 1) > 1 && <PriorityChip priority={req.priority ?? 1} />}
                    {req.due_date && (
                      <span
                        className={`inline-flex items-center rounded-pill border px-2 py-0.5 text-xs ${
                          isOverdue(req.due_date)
                            ? 'border-status-action/50 bg-status-action/10 font-semibold text-status-action'
                            : 'border-border text-text-secondary'
                        }`}
                      >
                        Due {fmtDate(req.due_date)}
                      </span>
                    )}
                    {req.company_eta && (
                      <span className="rounded-pill border border-border px-2 py-0.5 text-xs text-text-muted">
                        ETA {fmtDate(req.company_eta)}
                      </span>
                    )}
                    {(req.entity || req.period_from || req.period_to) && (
                      <span className="text-xs text-text-muted">
                        {[
                          req.entity,
                          req.period_from && req.period_to
                            ? `${fmtDate(req.period_from)} – ${fmtDate(req.period_to)}`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    )}
                    {req.responsible_person_name && (
                      <span className="rounded-pill border border-border px-2 py-0.5 text-xs text-text-secondary">
                        {req.responsible_person_name}
                      </span>
                    )}

                    <div className="ml-auto flex items-center gap-1.5">
                      {allKids.length > 0 && (
                        <button
                          onClick={() => setExpandedChildren((m) => ({ ...m, [req.id]: !open }))}
                          className="flex items-center gap-1 rounded-btn px-2 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-raised hover:text-text-primary"
                        >
                          <ChevronRight
                            className={`h-3.5 w-3.5 transition-transform duration-200 ease-spring ${open ? 'rotate-90' : ''}`}
                          />
                          {allKids.length} child{allKids.length === 1 ? '' : 'ren'}
                        </button>
                      )}
                      {req.latest_response?.document_id && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => void handleDownload(req.latest_response!.document_id!)}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                      )}
                      {req.responses.length > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setHistoryFor(historyFor === req.id ? null : req.id)}
                        >
                          <History className="h-4 w-4" /> {req.responses.length}
                        </Button>
                      )}
                      {canQuery && (
                        <button
                          title={
                            req.linked_query_count
                              ? `${req.linked_query_count} linked quer${
                                  req.linked_query_count === 1 ? 'y' : 'ies'
                                } — click to open another`
                              : 'Initiate query'
                          }
                          onClick={() => void handleInitiateQuery(req)}
                          disabled={createQuery.isPending}
                          className="relative flex h-7 w-7 items-center justify-center rounded-full border border-border text-text-muted transition-transform duration-150 ease-spring hover:scale-[1.15] hover:border-accent hover:text-accent active:scale-95 disabled:opacity-40"
                        >
                          <MessageSquarePlus className="h-3.5 w-3.5" />
                          {req.linked_query_count > 0 && (
                            <span className="absolute -right-1 -top-1 rounded-full bg-accent px-1 text-[10px] font-semibold leading-tight text-white">
                              {req.linked_query_count}
                            </span>
                          )}
                        </button>
                      )}
                      {req.status === 'submitted' && (
                        <>
                          <Button size="sm" onClick={() => void handleReview(req, 'accept')}>
                            Accept
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => setClarifyFor(clarifyFor === req.id ? null : req.id)}
                          >
                            Need clarification
                          </Button>
                        </>
                      )}
                      {req.status === 'pending' && (
                        <Button variant="ghost" size="sm" onClick={() => setDeleteTarget(req)}>
                          <Trash2 className="h-4 w-4 text-status-action" />
                        </Button>
                      )}
                    </div>
                  </div>

                  <p className="font-medium text-text-primary">{req.description}</p>

                  {req.status === 'clarification_needed' && req.clarification_note && (
                    <p className="animate-fade-in rounded-card border border-status-pending/40 bg-status-pending/10 px-3 py-2 text-sm">
                      Clarification requested: {req.clarification_note}
                    </p>
                  )}

                  <AnimatePresence>
                    {clarifyFor === req.id && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                      >
                        <div className="flex items-end gap-2 pt-1">
                          <Input
                            value={clarifyNote}
                            onChange={(e) => setClarifyNote(e.target.value)}
                            placeholder="What needs clarifying? (optional)"
                          />
                          <Button
                            size="sm"
                            disabled={review.isPending}
                            onClick={() =>
                              void handleReview(req, 'clarify', clarifyNote.trim() || undefined)
                            }
                          >
                            Send
                          </Button>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <AnimatePresence>
                    {historyFor === req.id && req.responses.length > 0 && (
                      <motion.ul
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden rounded-card border border-border bg-bg-raised/50 p-3 text-sm"
                      >
                        {req.responses.map((resp) => (
                          <li key={resp.id} className="flex items-start justify-between gap-3 py-1">
                            <div>
                              <p className="text-text-primary">{resp.text_answer}</p>
                              <p className="text-xs text-text-muted">
                                {new Date(resp.created_at).toLocaleString()}
                                {resp.responded_by_name ? ` · ${resp.responded_by_name}` : ''}
                              </p>
                            </div>
                            {resp.document_id && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => void handleDownload(resp.document_id!)}
                              >
                                <Download className="h-4 w-4" />
                              </Button>
                            )}
                          </li>
                        ))}
                      </motion.ul>
                    )}
                  </AnimatePresence>
                </Card>

                <AnimatePresence initial={false}>
                  {open &&
                    kids.map((kid) => (
                      <motion.div
                        key={kid.id}
                        layout
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0 }}
                        className="ml-8"
                      >
                        <ChildRow req={kid} onDownload={handleDownload} />
                      </motion.div>
                    ))}
                </AnimatePresence>
              </motion.div>
            )
          })}
        </AnimatePresence>
      )}

      {showCreate && (
        <NewRequirementModal
          engagementId={engagementId}
          nextReqId={nextReqId}
          companyUsers={[]}
          onClose={() => setShowCreate(false)}
        />
      )}
      {showImport && <BulkImportModal engagementId={engagementId} onClose={() => setShowImport(false)} />}
      {deleteTarget && (
        <ConfirmDialog
          open
          title={`Delete ${deleteTarget.requirement_id_str ?? 'requirement'}?`}
          message="Only pending requirements without children can be deleted."
          confirmLabel="Delete"
          destructive
          onConfirm={() => {
            del
              .mutateAsync({ engagementId, reqId: deleteTarget.id })
              .then(() => toast.success('Requirement deleted'))
              .catch((err) =>
                toast.error(err instanceof ApiError ? err.message : 'Error deleting'),
              )
              .finally(() => setDeleteTarget(null))
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}

function visibleRootFilter<T extends Req>(list: T[], filter: RequestStatusFilter | null): T[] {
  return filter ? list.filter((r) => r.status === filter) : list
}

function ChildRow({
  req,
  onDownload,
}: {
  req: Req
  onDownload: (docId: string) => Promise<void>
}) {
  return (
    <Card className="flex items-center justify-between gap-3 p-3">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="rounded-md bg-bg-raised px-1.5 py-0.5 font-mono text-xs text-text-muted">
          {req.requirement_id_str}
        </span>
        <StatusBadge status={req.status} />
        {(req.priority ?? 1) > 1 && <PriorityChip priority={req.priority ?? 1} />}
        <span className="truncate text-sm font-medium text-text-primary">{req.description}</span>
      </div>
      {req.latest_response?.document_id && (
        <Button variant="ghost" size="sm" onClick={() => void onDownload(req.latest_response!.document_id!)}>
          <Download className="h-4 w-4" />
        </Button>
      )}
    </Card>
  )
}
