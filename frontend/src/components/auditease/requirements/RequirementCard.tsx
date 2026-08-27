import React, { useState } from 'react'
import { clsx } from 'clsx'
import {
  Calendar,
  ChevronDown,
  Edit2,
  Lock,
  MessageSquare,
  RotateCcw,
  Trash2,
  User,
} from 'lucide-react'
import { Button } from '@/components/ui'
import type { RequirementRequestResponse } from '@/api/types'
import { PriorityChip } from './PriorityChip'
import { RequirementStatePill } from './RequirementStatePill'
import { StackedDocsBadge } from './StackedDocsBadge'
import { SubmissionTimeline } from './SubmissionTimeline'
import { RespondPanel } from './RespondPanel'
import { deriveDisplayState } from './progress'

interface RequirementCardProps {
  req: RequirementRequestResponse
  variant: 'auditor' | 'company'
  engagementId: string
  isExpanded?: boolean
  onToggleExpand?: () => void
  onEdit?: (req: RequirementRequestResponse) => void
  onDelete?: (req: RequirementRequestResponse) => void
  onClose?: (reqId: string) => void
  onReopen?: (reqId: string) => void
  onDownloadDoc?: (docId: string, filename: string) => void
  className?: string
}

export const RequirementCard: React.FC<RequirementCardProps> = ({
  req,
  variant,
  engagementId,
  isExpanded: controlledExpanded,
  onToggleExpand: controlledToggle,
  onEdit,
  onDelete,
  onClose,
  onReopen,
  onDownloadDoc,
  className,
}) => {
  const [internalExpanded, setInternalExpanded] = useState(false)
  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded
  const toggleExpand = controlledToggle || (() => setInternalExpanded((prev) => !prev))

  const displayState = deriveDisplayState(req)
  const isClosed = req.status === 'closed'
  const hasSubmissions = (req.submission_count ?? 0) > 0

  // Count total attached documents across all submissions
  const totalDocCount =
    req.document_count ??
    req.submissions?.reduce((acc, s) => acc + (s.documents?.length || 0), 0) ??
    0

  const isOverdue =
    req.due_date &&
    !isClosed &&
    new Date(`${req.due_date}T23:59:59`) < new Date()

  return (
    <div
      className={clsx(
        'rounded-xl border transition-all duration-200 bg-white dark:bg-zinc-900',
        isClosed
          ? 'border-zinc-200/80 bg-zinc-50/50 dark:border-zinc-800/80 dark:bg-zinc-900/40'
          : 'border-zinc-200 shadow-xs hover:border-zinc-300 dark:border-zinc-800 dark:hover:border-zinc-700',
        className
      )}
    >
      {/* Main Card Header / Content */}
      <div className="p-4">
        {/* Top Badges & Actions Row */}
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-bold text-zinc-900 dark:text-zinc-100 bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 rounded border border-zinc-200 dark:border-zinc-700">
              {req.requirement_id_str || 'REQ'}
            </span>
            <RequirementStatePill
              state={displayState}
              submissionCount={req.submission_count}
            />
            <PriorityChip priority={req.priority ?? 1} />
            <StackedDocsBadge count={totalDocCount} />

            {req.due_date && (
              <span
                className={clsx(
                  'inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded',
                  isOverdue
                    ? 'bg-red-50 text-red-700 border border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-800'
                    : 'text-zinc-500 dark:text-zinc-400'
                )}
                title={isOverdue ? 'Overdue' : 'Due date'}
              >
                <Calendar className="w-3 h-3" />
                <span>Due {req.due_date}</span>
                {isOverdue && <span className="font-bold">!</span>}
              </span>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1.5 ml-auto">
            {variant === 'auditor' && (
              <>
                {isClosed ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onReopen?.(req.id)}
                    className="gap-1 text-xs h-7 px-2.5"
                    title="Reopen requirement"
                  >
                    <RotateCcw className="w-3 h-3 text-blue-500" />
                    <span>Reopen</span>
                  </Button>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onClose?.(req.id)}
                    className="gap-1 text-xs h-7 px-2.5 text-zinc-700 hover:text-zinc-900 dark:text-zinc-300"
                    title="Close requirement"
                  >
                    <Lock className="w-3 h-3 text-zinc-500" />
                    <span>Close</span>
                  </Button>
                )}

                {!isClosed && onEdit && (
                  <button
                    type="button"
                    onClick={() => onEdit(req)}
                    className="p-1.5 rounded text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 dark:hover:text-zinc-200 dark:hover:bg-zinc-800 transition-colors"
                    title="Edit requirement"
                    aria-label="Edit requirement"
                  >
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                )}

                {!hasSubmissions && onDelete && (
                  <button
                    type="button"
                    onClick={() => onDelete(req)}
                    className="p-1.5 rounded text-zinc-400 hover:text-red-600 hover:bg-red-50 dark:hover:text-red-400 dark:hover:bg-red-950/40 transition-colors"
                    title="Delete requirement"
                    aria-label="Delete requirement"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </>
            )}

            <button
              type="button"
              onClick={toggleExpand}
              className="flex items-center gap-1 p-1.5 rounded text-xs font-medium text-zinc-500 hover:text-zinc-800 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:text-zinc-200 dark:hover:bg-zinc-800 transition-colors ml-1"
              aria-expanded={isExpanded}
              aria-label={isExpanded ? 'Collapse requirement' : 'Expand requirement'}
            >
              <ChevronDown
                className={clsx(
                  'w-4 h-4 transition-transform duration-200',
                  isExpanded ? 'rotate-180' : ''
                )}
              />
            </button>
          </div>
        </div>

        {/* Description */}
        <p
          className={clsx(
            'text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap leading-relaxed cursor-pointer',
            !isExpanded && 'line-clamp-2'
          )}
          onClick={toggleExpand}
        >
          {req.description}
        </p>

        {/* Metadata Footer */}
        <div className="mt-3 pt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-zinc-100 dark:border-zinc-800/80 text-[11px] text-zinc-400">
          <div className="flex flex-wrap items-center gap-3">
            {req.raised_by_name && (
              <span className="flex items-center gap-1">
                <User className="w-3 h-3" />
                <span>Raised by {req.raised_by_name}</span>
              </span>
            )}
            {isClosed && req.closed_at && (
              <span className="text-zinc-500 dark:text-zinc-400">
                Closed {new Date(req.closed_at).toLocaleDateString()}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={toggleExpand}
            className="flex items-center gap-1 text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 font-medium"
          >
            <MessageSquare className="w-3 h-3" />
            <span>
              {hasSubmissions
                ? `${req.submission_count} ${req.submission_count === 1 ? 'submission' : 'submissions'}`
                : 'No submissions'}
            </span>
          </button>
        </div>
      </div>

      {/* Expandable Accordion Body */}
      {isExpanded && (
        <div className="border-t border-zinc-200/80 bg-zinc-50/40 p-4 dark:border-zinc-800 dark:bg-zinc-900/60 space-y-4">
          <SubmissionTimeline
            submissions={req.submissions || []}
            onDownloadDoc={onDownloadDoc}
          />

          {variant === 'company' && (
            <RespondPanel
              engagementId={engagementId}
              req={req}
            />
          )}
        </div>
      )}
    </div>
  )
}
