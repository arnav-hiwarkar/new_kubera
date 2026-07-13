import React from 'react'
import { cn } from '@/lib/cn'

export interface SwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'onChange'> {
  checked?: boolean
  onChange?: (checked: boolean) => void
  label?: string
}

export function Switch({ checked = false, onChange, label, className, disabled, ...props }: SwitchProps) {
  return (
    <label className={cn('flex items-center gap-3 cursor-pointer', disabled && 'opacity-50 cursor-not-allowed', className)}>
      <div className="relative flex items-center">
        <input
          type="checkbox"
          className="sr-only"
          checked={checked}
          onChange={(e) => onChange?.(e.target.checked)}
          disabled={disabled}
          {...props}
        />
        <div
          className={cn(
            'block h-6 w-10 rounded-full transition-colors duration-200 ease-in-out',
            checked ? 'bg-accent' : 'bg-bg-raised border border-border'
          )}
        />
        <div
          className={cn(
            'absolute left-1 top-1 h-4 w-4 rounded-full bg-white transition-transform duration-200 ease-in-out',
            checked ? 'translate-x-4' : 'translate-x-0'
          )}
        />
      </div>
      {label && <span className="text-sm font-medium text-text-primary">{label}</span>}
    </label>
  )
}
