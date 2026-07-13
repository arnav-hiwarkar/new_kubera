import { useState, useRef, useEffect } from 'react'
import { cn } from '@/lib/cn'
import { useTheme } from '@/lib/useTheme'

export interface TopBarProps {
  /** Display name of the logged-in identity. */
  name: string
  /** Secondary line — role for company users, "Auditor" for auditors. */
  subtitle?: string
  onLogout: () => void
  accent?: 'company' | 'auditor'
}

export function TopBar({ name, subtitle, onLogout, accent = 'company' }: TopBarProps) {
  const { theme, toggle } = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const initials = name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <header className="flex h-topbar shrink-0 items-center justify-end gap-2 border-b border-border bg-bg-surface px-4">
      <button
        onClick={toggle}
        aria-label="Toggle theme"
        className="rounded-btn px-2 py-1 text-text-secondary hover:bg-bg-raised hover:text-text-primary"
      >
        {theme === 'dark' ? '☀' : '☾'}
      </button>
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 rounded-btn px-2 py-1 hover:bg-bg-raised"
        >
          <span
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold text-white',
              accent === 'auditor' ? 'bg-auditor' : 'bg-accent',
            )}
          >
            {initials || '?'}
          </span>
          <span className="hidden text-left sm:block">
            <span className="block text-sm font-medium leading-tight text-text-primary">
              {name}
            </span>
            {subtitle && (
              <span className="block text-xs capitalize leading-tight text-text-muted">
                {subtitle}
              </span>
            )}
          </span>
        </button>
        {open && (
          <div className="absolute right-0 top-full mt-1 w-40 rounded-card border border-border bg-bg-surface py-1 shadow-dropdown">
            <button
              onClick={onLogout}
              className="block w-full px-3 py-1.5 text-left text-sm text-text-primary hover:bg-bg-raised"
            >
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
