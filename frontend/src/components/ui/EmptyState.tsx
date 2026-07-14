import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export interface EmptyStateProps {
  title: string
  description?: string
  icon?: ReactNode
  action?: ReactNode
  className?: string
}

export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex animate-fade-in flex-col items-center justify-center rounded-card border border-dashed border-border bg-bg-surface px-6 py-14 text-center',
        className,
      )}
    >
      {icon && (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-subtle text-accent [&_svg]:h-6 [&_svg]:w-6">
          {icon}
        </div>
      )}
      <h3 className="text-md font-semibold text-text-primary">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-text-secondary">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
