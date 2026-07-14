import { useEffect, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
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

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-40 flex justify-end" role="presentation">
          <motion.div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onMouseDown={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className={cn(
              'relative flex h-full flex-col border-l border-border bg-bg-surface shadow-modal',
              widths[width],
            )}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
          >
            {title && (
              <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-3.5">
                <div className="min-w-0">
                  <h2 className="truncate text-md font-semibold text-text-primary">{title}</h2>
                  {subtitle && <div className="mt-0.5 text-sm text-text-secondary">{subtitle}</div>}
                </div>
                <button
                  onClick={onClose}
                  aria-label="Close"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-btn text-text-muted transition-colors hover:bg-bg-raised hover:text-text-primary"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
            <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
            {footer && (
              <div className="flex justify-end gap-2 border-t border-border px-5 py-3.5">{footer}</div>
            )}
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  )
}
