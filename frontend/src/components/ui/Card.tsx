import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function Card({
  children,
  className,
  hover,
}: {
  children: ReactNode
  className?: string
  /** Adds a subtle lift + border highlight on hover (for clickable cards). */
  hover?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-card border border-border bg-bg-surface p-5 shadow-card',
        hover &&
          'cursor-pointer transition-all duration-200 ease-spring hover:-translate-y-0.5 hover:border-border-strong hover:shadow-raised',
        className,
      )}
    >
      {children}
    </div>
  )
}

export interface PageHeaderProps {
  title: string
  description?: string
  /** Small uppercase label shown above the title. */
  eyebrow?: string
  /** Optional leading icon (e.g. a lucide icon) rendered in an accent chip. */
  icon?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ title, description, eyebrow, icon, actions }: PageHeaderProps) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        {icon && (
          <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-subtle text-accent [&_svg]:h-5 [&_svg]:w-5">
            {icon}
          </span>
        )}
        <div>
          {eyebrow && (
            <p className="mb-1 text-xs font-semibold uppercase tracking-[0.08em] text-accent">
              {eyebrow}
            </p>
          )}
          <h1 className="text-2xl font-bold tracking-display text-text-primary">{title}</h1>
          {description && <p className="mt-1 text-base text-text-secondary">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
