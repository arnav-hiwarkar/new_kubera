import { useEffect, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

export interface DrawerProps {
  open: boolean
  onClose: () => void
  title?: string
  subtitle?: ReactNode
  children: ReactNode
  footer?: ReactNode
  width?: 'md' | 'lg'
}

const widths = {
  md: 'w-full max-w-md',
  lg: 'w-full max-w-lg',
}

/**
 * Right-anchored slide-over panel. A distinct pattern from Modal (persistent
 * side surface, keeps the list in context) — reusable across modules that need
 * a detail/inspect surface without leaving the current view.
 */
export function Drawer({ open, onClose, title, subtitle, children, footer, width = 'lg' }: DrawerProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="presentation">
      <div className="absolute inset-0 bg-black/40" onMouseDown={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'relative flex h-full flex-col border-l border-border bg-bg-surface shadow-modal',
          widths[width],
        )}
      >
        {title && (
          <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-3">
            <div className="min-w-0">
              <h2 className="truncate text-md font-semibold text-text-primary">{title}</h2>
              {subtitle && <div className="mt-0.5 text-sm text-text-secondary">{subtitle}</div>}
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="shrink-0 text-lg leading-none text-text-muted hover:text-text-primary"
            >
              ×
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>
        )}
      </aside>
    </div>
  )
}
