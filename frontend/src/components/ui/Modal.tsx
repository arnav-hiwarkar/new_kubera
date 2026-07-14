import { useEffect, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { cn } from '@/lib/cn'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
}

const sizes = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
}

export function Modal({ open, onClose, title, children, footer, size = 'md' }: ModalProps) {
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
        <motion.div
          className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-[10vh] backdrop-blur-sm"
          onMouseDown={onClose}
          role="presentation"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            onMouseDown={(e) => e.stopPropagation()}
            className={cn(
              'w-full rounded-card border border-border bg-bg-surface shadow-modal',
              sizes[size],
            )}
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 6 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          >
            {title && (
              <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
                <h2 className="text-md font-semibold text-text-primary">{title}</h2>
                <button
                  onClick={onClose}
                  aria-label="Close"
                  className="flex h-7 w-7 items-center justify-center rounded-btn text-text-muted transition-colors hover:bg-bg-raised hover:text-text-primary"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
            <div className="px-5 py-4">{children}</div>
            {footer && (
              <div className="flex justify-end gap-2 border-t border-border px-5 py-3.5">{footer}</div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
