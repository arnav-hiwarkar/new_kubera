import React from 'react'
import { clsx } from 'clsx'
import { Paperclip } from 'lucide-react'

interface StackedDocsBadgeProps {
  count: number
  className?: string
}

export const StackedDocsBadge: React.FC<StackedDocsBadgeProps> = ({ count, className }) => {
  if (count <= 0) return null

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium',
        'bg-zinc-100 text-zinc-600 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700',
        className
      )}
      title={`${count} attached ${count === 1 ? 'document' : 'documents'}`}
    >
      <Paperclip className="w-3 h-3 text-zinc-400" />
      <span>{count} {count === 1 ? 'doc' : 'docs'}</span>
    </span>
  )
}
