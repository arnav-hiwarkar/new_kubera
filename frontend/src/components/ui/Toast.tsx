import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
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
        {toasts.map((t) => (
          <div
            key={t.id}
            role="alert"
            className={cn(
              'pointer-events-auto flex items-start gap-2 rounded-card border bg-bg-surface p-3 text-sm shadow-dropdown',
              t.variant === 'success' && 'border-status-verified/40',
              t.variant === 'error' && 'border-status-action/40',
              t.variant === 'info' && 'border-accent/40',
            )}
          >
            <span
              className={cn(
                'mt-1 h-2 w-2 shrink-0 rounded-full',
                t.variant === 'success' && 'bg-status-verified',
                t.variant === 'error' && 'bg-status-action',
                t.variant === 'info' && 'bg-accent',
              )}
            />
            <span className="flex-1 text-text-primary">{t.message}</span>
            <button
              onClick={() => remove(t.id)}
              className="text-text-muted hover:text-text-primary"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
