import { useState, useRef, useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Search, Moon, Sun, LogOut, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useTheme } from '@/lib/useTheme'
import { CommandPalette } from './CommandPalette'
import type { NavSection } from './Sidebar'

export interface TopBarProps {
  /** Display name of the logged-in identity. */
  name: string
  /** Secondary line — role for company users, "Auditor" for auditors. */
  subtitle?: string
  onLogout: () => void
  accent?: 'company' | 'auditor'
  /** Nav sections powering the ⌘K command palette. */
  sections?: NavSection[]
}

export function TopBar({ name, subtitle, onLogout, accent = 'company', sections = [] }: TopBarProps) {
  const { theme, toggle } = useTheme()
  const [open, setOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((o) => !o)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const initials = name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  const avatarGrad = accent === 'auditor' ? 'from-auditor to-auditor-hover' : 'from-accent to-accent-active'

  return (
    <header className="glass sticky top-0 z-30 flex h-topbar shrink-0 items-center justify-between gap-2 border-b px-4">
      {/* Search / command trigger */}
      <button
        onClick={() => setPaletteOpen(true)}
        className="group flex h-9 items-center gap-2 rounded-btn border border-border-strong bg-bg-surface/60 px-3 text-sm text-text-muted transition-colors hover:border-accent/40 hover:text-text-secondary"
      >
        <Search className="h-4 w-4" />
        <span className="hidden sm:block">Search…</span>
        <kbd className="ml-1 hidden rounded border border-border bg-bg-raised px-1.5 py-0.5 font-mono text-[10px] font-medium sm:block">
          ⌘K
        </kbd>
      </button>

      <div className="flex items-center gap-1.5">
        <button
          onClick={toggle}
          aria-label="Toggle theme"
          className="flex h-9 w-9 items-center justify-center rounded-btn text-text-secondary transition-colors hover:bg-bg-raised hover:text-text-primary"
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={theme}
              initial={{ rotate: -40, opacity: 0, scale: 0.8 }}
              animate={{ rotate: 0, opacity: 1, scale: 1 }}
              exit={{ rotate: 40, opacity: 0, scale: 0.8 }}
              transition={{ duration: 0.2 }}
            >
              {theme === 'dark' ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
            </motion.span>
          </AnimatePresence>
        </button>

        <div ref={ref} className="relative">
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-2 rounded-btn py-1 pl-1 pr-2 transition-colors hover:bg-bg-raised"
          >
            <span
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br text-xs font-semibold text-white shadow-sm',
                avatarGrad,
              )}
            >
              {initials || '?'}
            </span>
            <span className="hidden text-left sm:block">
              <span className="block text-sm font-semibold leading-tight text-text-primary">{name}</span>
              {subtitle && (
                <span className="block text-xs capitalize leading-tight text-text-muted">{subtitle}</span>
              )}
            </span>
            <ChevronDown className="hidden h-4 w-4 text-text-muted sm:block" />
          </button>
          <AnimatePresence>
            {open && (
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -4, scale: 0.98 }}
                transition={{ duration: 0.16 }}
                className="absolute right-0 top-full mt-2 w-52 overflow-hidden rounded-card border border-border bg-bg-surface py-1 shadow-dropdown"
              >
                <div className="border-b border-border px-3 py-2 sm:hidden">
                  <p className="text-sm font-semibold text-text-primary">{name}</p>
                  {subtitle && <p className="text-xs capitalize text-text-muted">{subtitle}</p>}
                </div>
                <button
                  onClick={onLogout}
                  className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-text-primary transition-colors hover:bg-bg-raised"
                >
                  <LogOut className="h-4 w-4 text-text-muted" />
                  Log out
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        sections={sections}
        accent={accent}
        onLogout={onLogout}
      />
    </header>
  )
}
