import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

/** Wraps a form control with label, required marker, and inline error/hint display. */
export interface FieldProps {
  label?: string
  htmlFor?: string
  required?: boolean
  error?: string
  hint?: string
  children: ReactNode
  className?: string
}

export function Field({ label, htmlFor, required, error, hint, children, className }: FieldProps) {
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      {label && (
        <label htmlFor={htmlFor} className="text-sm font-medium text-text-secondary">
          {label}
          {required && <span className="ml-0.5 text-status-action">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="text-xs text-status-action">{error}</p>
      ) : hint ? (
        <p className="text-xs text-text-muted">{hint}</p>
      ) : null}
    </div>
  )
}

const controlBase =
  'w-full rounded-input border border-border bg-bg-surface px-3 py-2 text-base text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-60 aria-[invalid=true]:border-status-action'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { error?: boolean }>(
  function Input({ className, error, ...props }, ref) {
    return (
      <input
        ref={ref}
        aria-invalid={error || undefined}
        className={cn(controlBase, 'h-9', className)}
        {...props}
      />
    )
  },
)

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & { error?: boolean }>(
  function Textarea({ className, error, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        aria-invalid={error || undefined}
        className={cn(controlBase, 'min-h-[80px]', className)}
        {...props}
      />
    )
  },
)

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & { error?: boolean }>(
  function Select({ className, error, children, ...props }, ref) {
    return (
      <select
        ref={ref}
        aria-invalid={error || undefined}
        className={cn(controlBase, 'h-9', className)}
        {...props}
      >
        {children}
      </select>
    )
  },
)
