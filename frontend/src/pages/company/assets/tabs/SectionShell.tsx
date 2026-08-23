import type { ReactNode } from 'react'
import { Calculator } from 'lucide-react'
import { Button } from '@/components/ui'
import { cn } from '@/lib/cn'

export interface SectionShellProps {
  title?: string
  description?: string
  children: ReactNode
  dirty: boolean
  saving: boolean
  onSave: () => void
  onReset: () => void
  /** Rendered instead of the save controls when the section cannot be edited. */
  readOnlyNote?: string
  className?: string
}

/**
 * One savable section of the asset detail page. Each tab saves independently so a
 * user can fill in depreciation without carrying a half-typed invoice number along,
 * and the footer only appears once something has actually changed.
 */
export function SectionShell({
  title,
  description,
  children,
  dirty,
  saving,
  onSave,
  onReset,
  readOnlyNote,
  className,
}: SectionShellProps) {
  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {(title || description) && (
        <div>
          {title && <h3 className="text-md font-semibold text-text-primary">{title}</h3>}
          {description && <p className="mt-0.5 text-sm text-text-muted">{description}</p>}
        </div>
      )}

      {readOnlyNote && (
        <p className="rounded-card border border-border bg-bg-raised px-3 py-2 text-sm text-text-secondary">
          {readOnlyNote}
        </p>
      )}

      {children}

      {dirty && !readOnlyNote && (
        <div className="sticky bottom-0 -mx-1 flex items-center justify-end gap-2 border-t border-border bg-bg-surface/95 px-1 py-3 backdrop-blur">
          <span className="mr-auto text-sm text-text-muted">Unsaved changes</span>
          <Button variant="ghost" onClick={onReset} disabled={saving}>
            Discard
          </Button>
          <Button onClick={onSave} loading={saving}>
            Save
          </Button>
        </div>
      )}
    </div>
  )
}

/** Read-only label/value row, for figures the system derives. */
export function DerivedRow({
  label,
  value,
  hint,
  emphasis,
  onExplain,
}: {
  label: string
  value: ReactNode
  hint?: string
  emphasis?: boolean
  /** Opens this figure's step in the calculation drawer. */
  onExplain?: () => void
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <div>
        <span className={cn('text-sm', emphasis ? 'font-medium text-text-primary' : 'text-text-secondary')}>
          {label}
        </span>
        {hint && <p className="text-xs text-text-muted">{hint}</p>}
      </div>
      <span className="flex items-baseline gap-1.5">
        <span
          className={cn(
            'tabular-nums',
            emphasis ? 'text-md font-semibold text-text-primary' : 'text-sm text-text-primary',
          )}
        >
          {value}
        </span>
        {/* A bare icon rather than a labelled link: these rows come in runs of six or
            more, and a link on each would crowd out the figures. */}
        {onExplain && (
          <button
            type="button"
            onClick={onExplain}
            aria-label={`How was ${label} calculated?`}
            className="rounded-btn p-0.5 text-text-muted hover:bg-bg-raised hover:text-accent focus:outline-none focus:ring-1 focus:ring-accent"
          >
            <Calculator className="h-3.5 w-3.5" />
          </button>
        )}
      </span>
    </div>
  )
}
