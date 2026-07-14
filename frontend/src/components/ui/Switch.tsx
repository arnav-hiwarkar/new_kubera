import React from 'react'
import { cn } from '@/lib/cn'

export interface SwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'onChange'> {
  checked?: boolean
  onChange?: (checked: boolean) => void
  label?: string
}

export function Switch({ checked = false, onChange, label, className, disabled, ...props }: SwitchProps) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-center gap-3',
        disabled && 'cursor-not-allowed opacity-50',
        className,
      )}
    >
      <div className="relative flex items-center">
        <input
          type="checkbox"
          className="peer sr-only"
          checked={checked}
          onChange={(e) => onChange?.(e.target.checked)}
          disabled={disabled}
          {...props}
        />
        <div
          className={cn(
            'block h-6 w-11 rounded-full transition-colors duration-200 ease-spring peer-focus-visible:ring-2 peer-focus-visible:ring-accent/40 peer-focus-visible:ring-offset-1 peer-focus-visible:ring-offset-bg-surface',
            checked ? 'bg-accent-gradient' : 'border border-border-strong bg-bg-raised',
          )}
        />
        <div
          className={cn(
            'absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-transform duration-200 ease-spring',
            checked ? 'translate-x-5' : 'translate-x-0',
          )}
        />
      </div>
      {label && <span className="text-sm font-medium text-text-primary">{label}</span>}
    </label>
  )
}
