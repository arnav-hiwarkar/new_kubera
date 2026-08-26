import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CalendarClock, Download, Paperclip } from 'lucide-react'
import {
  Button,
  Card,
  EmptyState,
  Select,
  Spinner,
  StatusBadge,
  Textarea,
  useToast,
} from '@/components/ui'
import { ApiError } from '@/api/http'
import {
  useListRequirements,
  useRespondToRequirement,
  useSetRequirementEta,
} from '@/api/hooks/auditease'
import { useDocuments, useDownloadDocument } from '@/api/hooks/docvault'
import { useMe } from '@/api/hooks/users'
import type { RequirementRequestResponse } from '@/api/types'
import {
  RequirementsProgress,
  type RequestStatusFilter,
} from '@/components/auditease/requirements/RequirementsProgress'
import { PriorityChip } from '@/components/auditease/requirements/PriorityChip'

type Req = RequirementRequestResponse

function fmtDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function RequirementsTab({ engagementId }: { engagementId: string }) {
  const toast = useToast()
  const { data: reqs = [], isLoading } = useListRequirements(engagementId)
  const { data: docs = [] } = useDocuments()
  const downloadDoc = useDownloadDocument()
  const respond = useRespondToRequirement()
  const setEta = useSetRequirementEta()
  const { data: me } = useMe()
  const currentUserId = me?.id

  const [filter, setFilter] = useState<RequestStatusFilter | null>(null)
  const [respondFor, setRespondFor] = useState<string | null>(null)
  const [textAnswer, setTextAnswer] = useState('')
  const [selectedDoc, setSelectedDoc] = useState('')

  const visible = filter ? reqs.filter((r) => r.status === filter) : reqs

  const handleRespond = async (req: Req) => {
    if (!textAnswer.trim() && !selectedDoc) {
      toast.error('Type an answer or attach a document')
      return
    }
    try {
      await respond.mutateAsync({
        engagementId,
        reqId: req.id,
        body: {
          text_answer: textAnswer.trim() || undefined,
          document_id: selectedDoc || undefined,
        },
      })
      toast.success(`Response submitted for ${req.requirement_id_str}`)
      setRespondFor(null)
      setTextAnswer('')
      setSelectedDoc('')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Error submitting response')
    }
  }

  const handleEta = async (req: Req, value: string) => {
    try {
      await setEta.mutateAsync({
        engagementId,
        reqId: req.id,
        body: { company_eta: value || null },
      })
      toast.success(value ? `ETA set for ${req.requirement_id_str}` : 'ETA cleared')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not set ETA')
    }
  }

  const handleDownload = async (docId: string) => {
    const doc = docs.find((d) => d.id === docId)
    const version = doc?.versions.find((v) => v.id === doc.current_version_id)
    if (!doc || !version) {
      toast.error('Document not found')
      return
    }
    try {
      await downloadDoc.mutateAsync({
        id: doc.id,
        versionId: version.id,
        filename: version.original_filename,
      })
    } catch {
      toast.error('Failed to download document')
    }
  }

  if (isLoading) return <Spinner className="mx-auto mt-8 h-6 w-6" />

  const canRespondTo = (r: Req) => r.status === 'pending' || r.status === 'clarification_needed'

  return (
    <div className="flex flex-col gap-4">
      <RequirementsProgress requirements={reqs} activeFilter={filter} onFilterChange={setFilter} />

      {visible.length === 0 ? (
        <EmptyState
          title={reqs.length === 0 ? 'No requirements' : 'Nothing with this status'}
          description={
            reqs.length === 0
              ? "The auditor hasn't requested anything yet."
              : 'Try another status filter.'
          }
        />
      ) : (
        visible.map((req) => {
          const open = respondFor === req.id
          const mine = currentUserId && req.responsible_person_id === currentUserId
          return (
            <Card key={req.id} className="flex animate-fade-in-up flex-col gap-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-bg-raised px-1.5 py-0.5 font-mono text-xs text-text-secondary">
                  {req.requirement_id_str}
                </span>
                <StatusBadge status={req.status} />
                {(req.priority ?? 1) > 1 && <PriorityChip priority={req.priority ?? 1} />}
                {mine ? (
                  <span className="rounded-pill border border-accent/50 bg-accent-subtle px-2 py-0.5 text-xs font-medium text-accent">
                    You're responsible
                  </span>
                ) : null}
                {req.due_date && (
                  <span className="text-xs font-medium text-text-secondary">
                    Due {fmtDate(req.due_date)}
                  </span>
                )}
                {(req.entity || (req.period_from && req.period_to)) && (
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
              </div>

              <p className="font-medium text-text-primary">{req.description}</p>

              {req.expected_format !== 'any' && (
                <p className="text-xs text-text-muted">
                  Auditor expects:{' '}
                  {req.expected_format === 'text' ? 'a typed answer' : 'a document'} — you can always
                  provide either or both.
                </p>
              )}

              {req.status === 'clarification_needed' && req.clarification_note && (
                <p className="animate-fade-in rounded-card border border-status-pending/40 bg-status-pending/10 px-3 py-2 text-sm">
                  <strong>Clarification needed:</strong> {req.clarification_note}
                </p>
              )}

              <div className="flex flex-wrap items-center gap-2">
                {req.company_eta ? (
                  <span className="inline-flex items-center gap-1 rounded-pill border border-border px-2 py-0.5 text-xs text-text-secondary">
                    <CalendarClock className="h-3.5 w-3.5" /> ETA {fmtDate(req.company_eta)}
                  </span>
                ) : null}
                {canRespondTo(req) && (
                  <label className="inline-flex cursor-pointer items-center gap-1 rounded-pill border border-dashed border-border-strong px-2 py-0.5 text-xs text-text-muted transition-colors hover:border-accent hover:text-accent">
                    <CalendarClock className="h-3.5 w-3.5" />
                    {req.company_eta ? 'Change ETA' : 'Set expected by'}
                    <input
                      type="date"
                      className="sr-only"
                      value={req.company_eta ?? ''}
                      onChange={(e) => void handleEta(req, e.target.value)}
                    />
                  </label>
                )}

                {req.latest_response?.document_id && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void handleDownload(req.latest_response!.document_id!)}
                  >
                    <Download className="h-4 w-4" /> Document
                  </Button>
                )}

                {canRespondTo(req) && !open && (
                  <Button
                    size="sm"
                    className="ml-auto"
                    onClick={() => {
                      setRespondFor(req.id)
                      setTextAnswer('')
                      setSelectedDoc('')
                    }}
                  >
                    Respond
                  </Button>
                )}
              </div>

              <AnimatePresence>
                {open && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="animate-scale-in flex flex-col gap-3 rounded-card border border-border bg-bg-raised/40 p-3">
                      <Textarea
                        rows={3}
                        autoFocus
                        value={textAnswer}
                        onChange={(e) => setTextAnswer(e.target.value)}
                        placeholder="Type your answer…"
                      />
                      <div className="flex items-end gap-2">
                        <Select
                          value={selectedDoc}
                          onChange={(e) => setSelectedDoc(e.target.value)}
                          className="flex-1"
                        >
                          <option value="">Attach from docVault…</option>
                          {docs.map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.title}
                            </option>
                          ))}
                        </Select>
                        <Paperclip className="mb-2.5 h-4 w-4 shrink-0 text-text-muted" />
                      </div>
                      <div className="flex items-center justify-end gap-2">
                        <Button variant="secondary" size="sm" onClick={() => setRespondFor(null)}>
                          Cancel
                        </Button>
                        <Button size="sm" disabled={respond.isPending} onClick={() => void handleRespond(req)}>
                          {respond.isPending ? 'Submitting…' : 'Submit'}
                        </Button>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </Card>
          )
        })
      )}
    </div>
  )
}
