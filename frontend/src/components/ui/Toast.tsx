import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'
import { cn } from '@/lib/cn'

type ToastVariant = 'success' | 'error' | 'info'
interface Toast {
  id: number
  message: string
  variant: ToastVariant
}

interface ToastApi {
  toast: (message: string, variant?: ToastVariant) => void
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const variantStyles: Record<ToastVariant, { border: string; icon: ReactNode }> = {
  success: { border: 'border-status-verified/40', icon: <CheckCircle2 className="h-4 w-4 text-status-verified" /> },
  error: { border: 'border-status-action/40', icon: <XCircle className="h-4 w-4 text-status-action" /> },
  info: { border: 'border-accent/40', icon: <Info className="h-4 w-4 text-accent" /> },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const remove = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const toast = useCallback(
    (message: string, variant: ToastVariant = 'info') => {
      const id = nextId.current++
      setToasts((t) => [...t, { id, message, variant }])
      setTimeout(() => remove(id), 4500)
    },
    [remove],
  )

  const api = useMemo<ToastApi>(
    () => ({
      toast,
      success: (m) => toast(m, 'success'),
      error: (m) => toast(m, 'error'),
      info: (m) => toast(m, 'info'),
    }),
    [toast],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              role="alert"
              layout
              initial={{ opacity: 0, y: 16, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: 32, scale: 0.95 }}
              transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
              className={cn(
                'pointer-events-auto flex items-start gap-2.5 rounded-card border bg-bg-surface p-3.5 text-sm shadow-dropdown',
                variantStyles[t.variant].border,
              )}
            >
              <span className="mt-0.5 shrink-0">{variantStyles[t.variant].icon}</span>
              <span className="flex-1 text-text-primary">{t.message}</span>
              <button
                onClick={() => remove(t.id)}
                className="text-text-muted transition-colors hover:text-text-primary"
                aria-label="Dismiss"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
