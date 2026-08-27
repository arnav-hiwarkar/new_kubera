import React from 'react'
import { clsx } from 'clsx'
import { User, Calendar } from 'lucide-react'
import type { RequirementSubmissionOut } from '@/api/types'
import { DocumentChip } from './DocumentChip'

interface SubmissionTimelineProps {
  submissions: RequirementSubmissionOut[]
  onDownloadDoc?: (docId: string, filename: string) => void
  className?: string
}

export const SubmissionTimeline: React.FC<SubmissionTimelineProps> = ({
  submissions,
  onDownloadDoc,
  className,
}) => {
  if (!submissions || submissions.length === 0) {
    return (
      <div className={clsx('text-xs text-zinc-400 italic py-2', className)}>
        No responses submitted yet.
      </div>
    )
  }

  // Reverse chronological: newest round at the top
  const sortedSubmissions = [...submissions].sort(
    (a, b) => (b.round_number ?? 0) - (a.round_number ?? 0)
  )

  return (
    <div className={clsx('space-y-4 pt-2', className)}>
      <h4 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
        Submission History ({submissions.length} {submissions.length === 1 ? 'round' : 'rounds'})
      </h4>

      <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-zinc-200 dark:before:bg-zinc-800">
        {sortedSubmissions.map((sub, idx) => (
          <div key={sub.id} className="relative group">
            {/* Timeline Dot */}
            <div className="absolute -left-6 top-1 w-5 h-5 rounded-full border-2 border-white bg-blue-500 dark:border-zinc-900 shadow-sm flex items-center justify-center text-[10px] font-bold text-white">
              {sub.round_number}
            </div>

            <div className="rounded-lg border border-zinc-200 bg-zinc-50/70 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900/60 shadow-xs">
              {/* Header */}
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-2 border-b border-zinc-200/60 dark:border-zinc-800/60">
                <div className="flex items-center gap-1.5 font-medium text-zinc-800 dark:text-zinc-200">
                  <span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 font-semibold text-[10px]">
                    Round {sub.round_number}
                  </span>
                  {idx === 0 && sortedSubmissions.length > 1 && (
                    <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 font-medium text-[10px]">
                      Latest
                    </span>
                  )}
                  {sub.responded_by_name && (
                    <span className="flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
                      <User className="w-3 h-3 text-zinc-400" />
                      {sub.responded_by_name}
                    </span>
                  )}
                </div>
                {sub.created_at && (
                  <span className="flex items-center gap-1 text-[11px] text-zinc-400">
                    <Calendar className="w-3 h-3" />
                    {new Date(sub.created_at).toLocaleString(undefined, {
                      dateStyle: 'medium',
                      timeStyle: 'short',
                    })}
                  </span>
                )}
              </div>

              {/* Text answer */}
              {sub.text_answer && (
                <div className="text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap leading-relaxed mb-3">
                  {sub.text_answer}
                </div>
              )}

              {/* Document attachments */}
              {sub.documents && sub.documents.length > 0 && (
                <div className="mt-2">
                  <div className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400 mb-1.5">
                    Attached Documents ({sub.documents.length}):
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {sub.documents.map((doc, idx) => (
                      <DocumentChip
                        key={doc.document_id || `${sub.id}-doc-${idx}`}
                        doc={doc}
                        onDownload={onDownloadDoc}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
