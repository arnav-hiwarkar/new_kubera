import { Clock, CheckCircle2, AlertTriangle, MessageSquareQuote } from 'lucide-react'
import { Button, Field, Input } from '@/components/ui'
import { cn } from '@/lib/cn'
import { formatDate } from '@/lib/format'
import type { DocumentResponse } from '@/api/types'
import { ApproverPicker } from './ApproverPicker'
import type { DocumentActions } from './useDocumentActions'

/**
 * The approval section of a document: the pending-review block, the resolved
 * review note, and the submit/resubmit card. Shared by DocumentDrawer and
 * GraphDocumentInspector — it is the one piece of approval presentation
 * intricate enough that writing it twice is how the two surfaces drifted apart
 * in the first place.
 */
export function DocumentApprovalPanel({
  document,
  actions,
}: {
  document: DocumentResponse
  actions: DocumentActions
}) {
  const { isPending, canReview, canRequestApproval } = actions

  return (
    <>
      {isPending && (
        <div className="rounded-card border border-amber-500/30 bg-amber-500/5 p-4 flex flex-col gap-3">
          <div className="flex items-start gap-2.5">
            <Clock className="h-5 w-5 shrink-0 text-amber-400 mt-0.5" />
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-semibold text-text-primary">
                {canReview ? 'Review & Approval Required' : 'Awaiting Document Approval'}
              </h4>
              <p className="text-xs text-text-muted mt-0.5">
                {canReview
                  ? `Requested by ${document.created_by_name || 'team member'} ${
                      document.approval_requested_at
                        ? `on ${formatDate(document.approval_requested_at)}`
                        : ''
                    }`
                  : `Assigned to ${
                      document.approver_name || 'the designated approver'
                    }. Edits are paused until review is completed.`}
              </p>
            </div>
          </div>

          {canReview && (
            <div className="flex flex-col gap-3 pt-2 border-t border-amber-500/20">
              <Field
                label="Review notes / feedback"
                htmlFor="approval-notes"
                hint="Optional for approval; required when requesting changes"
              >
                <Input
                  id="approval-notes"
                  value={actions.notes}
                  onChange={(e) => actions.setNotes(e.target.value)}
                  placeholder="e.g. Verified compliance checklist, ready for submission"
                  disabled={actions.isReviewing}
                />
              </Field>

              <div className="flex flex-wrap items-center gap-2.5 pt-1">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={actions.handleApprove}
                  loading={actions.isReviewing}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white"
                >
                  <CheckCircle2 className="h-4 w-4 mr-1.5" />
                  Approve (Verified)
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={actions.handleRequestChanges}
                  loading={actions.isReviewing}
                  className="border-amber-500/40 text-amber-400 hover:bg-amber-500/10"
                >
                  <AlertTriangle className="h-4 w-4 mr-1.5" />
                  Request Changes
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {!isPending && document.approval_notes && (
        <div
          className={cn(
            'rounded-card border p-3 flex items-start gap-2.5',
            document.status === 'action_required'
              ? 'border-amber-500/40 bg-amber-500/10'
              : 'border-border bg-bg-surface',
          )}
        >
          <MessageSquareQuote
            className={cn(
              'h-4 w-4 shrink-0 mt-0.5',
              document.status === 'action_required' ? 'text-amber-400' : 'text-accent',
            )}
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                {document.status === 'action_required' ? 'Requested Changes Note' : 'Review Note'} ·{' '}
                {document.approver_name || 'Approver'}
              </span>
              {document.approved_at && (
                <span className="text-xs text-text-muted">{formatDate(document.approved_at)}</span>
              )}
            </div>
            <p className="text-sm text-text-primary mt-1">{document.approval_notes}</p>
          </div>
        </div>
      )}

      {canRequestApproval && (
        <div className="rounded-card border border-accent/30 bg-accent/5 p-4 flex flex-col gap-3">
          <div className="flex items-start gap-2.5">
            <Clock className="h-5 w-5 shrink-0 text-accent mt-0.5" />
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-semibold text-text-primary">
                {document.status === 'action_required' ? 'Resubmit for Review' : 'Submit for Review'}
              </h4>
              <p className="text-xs text-text-muted mt-0.5">
                {document.status === 'action_required'
                  ? 'Once revisions are complete, resubmit this document for approval.'
                  : 'Request an approver to review and verify this document.'}
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-2 pt-2 border-t border-accent/20">
            <Field label="Assign Approver">
              <ApproverPicker
                value={actions.approverId}
                onChange={actions.setApproverId}
                bucketId={document.bucket_id}
                disabled={actions.isRequesting || !actions.canAssignApprover}
              />
            </Field>
            <div className="flex justify-end pt-1">
              <Button
                variant="primary"
                size="sm"
                onClick={actions.handleRequestApproval}
                loading={actions.isRequesting}
                disabled={!actions.approverId && !document.approver_id}
              >
                {document.status === 'action_required'
                  ? 'Resubmit for Approval'
                  : 'Submit for Approval'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
