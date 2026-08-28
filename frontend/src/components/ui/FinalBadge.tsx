import { cn } from '@/lib/cn'

export interface FinalBadgeProps {
  className?: string
}

export function FinalBadge({ className }: FinalBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-400',
        className,
      )}
      title="This document is Final (locked from edits and new versions)"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)] animate-pulse" />
      Final
    </span>
  )
}
