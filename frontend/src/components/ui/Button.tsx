import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'
import { Spinner } from './Spinner'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle' | 'gold'
type Size = 'sm' | 'md' | 'lg' | 'icon'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

const variants: Record<Variant, string> = {
  primary:
    'bg-accent-gradient text-accent-contrast shadow-sm hover:brightness-[1.06] hover:shadow-glow active:brightness-95 disabled:opacity-50',
  secondary:
    'bg-bg-surface text-text-primary border border-border-strong hover:bg-bg-raised hover:border-border-strong disabled:opacity-50',
  ghost: 'text-text-secondary hover:bg-bg-raised hover:text-text-primary disabled:opacity-50',
  subtle: 'bg-accent-subtle text-accent hover:brightness-[0.97] disabled:opacity-50',
  danger: 'bg-status-action text-white shadow-sm hover:brightness-105 active:brightness-95 disabled:opacity-50',
  gold: 'bg-gold text-white shadow-sm hover:brightness-105 active:brightness-95 disabled:opacity-50',
}

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-9 px-4 text-base',
  lg: 'h-11 px-6 text-md',
  icon: 'h-9 w-9 p-0',
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
        'inline-flex items-center justify-center gap-2 rounded-btn font-semibold transition-all duration-150 ease-spring',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-1 focus-visible:ring-offset-bg-surface',
        'active:scale-[0.98] disabled:cursor-not-allowed disabled:active:scale-100',
        '[&_svg]:h-4 [&_svg]:w-4 [&_svg]:shrink-0',
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
