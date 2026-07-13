import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'
import { Spinner } from './Spinner'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

const variants: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:bg-accent-hover disabled:bg-accent/50',
  secondary:
    'bg-bg-surface text-text-primary border border-border hover:bg-bg-raised disabled:opacity-50',
  ghost: 'text-text-secondary hover:bg-bg-raised hover:text-text-primary disabled:opacity-50',
  danger: 'bg-status-action text-white hover:opacity-90 disabled:opacity-50',
}

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-9 px-4 text-base',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading, disabled, className, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-btn font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {loading && <Spinner className="h-4 w-4 text-current" />}
      {children}
    </button>
  )
})
