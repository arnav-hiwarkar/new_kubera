import React from 'react'
import { clsx } from 'clsx'
import { CheckCircle2, Clock, MessageSquareQuote } from 'lucide-react'
import type { RequirementDisplayState } from './progress'

interface RequirementStatePillProps {
  state: RequirementDisplayState
  submissionCount?: number
  className?: string
}

export const RequirementStatePill: React.FC<RequirementStatePillProps> = ({
  state,
  submissionCount,
  className,
}) => {
  if (state === 'closed') {
    return (
      <span
        className={clsx(
          'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border',
          'bg-zinc-100 text-zinc-700 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700',
          className
        )}
      >
        <CheckCircle2 className="w-3.5 h-3.5 text-zinc-500 dark:text-zinc-400" />
        <span>Closed</span>
      </span>
    )
  }

  if (state === 'responded') {
    const label =
      submissionCount && submissionCount > 1
        ? `Responded (R${submissionCount})`
        : 'Responded'

    return (
      <span
        className={clsx(
          'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border',
          'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800/60',
          className
        )}
      >
        <MessageSquareQuote className="w-3.5 h-3.5 text-blue-500" />
        <span>{label}</span>
      </span>
    )
  }

  // 'awaiting'
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border',
        'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800/60',
        className
      )}
    >
      <Clock className="w-3.5 h-3.5 text-amber-500" />
      <span>Awaiting Response</span>
    </span>
  )
}
