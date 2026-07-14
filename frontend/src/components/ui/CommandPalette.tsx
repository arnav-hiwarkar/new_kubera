import { useEffect, useMemo, useRef, useState, type ComponentType } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Search, CornerDownLeft, Moon, Sun, LogOut } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { NavSection } from './Sidebar'
import { useTheme } from '@/lib/useTheme'

interface Command {
  id: string
  label: string
  hint?: string
  icon?: ComponentType<{ className?: string }>
  run: () => void
}

export interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  sections: NavSection[]
  accent?: 'company' | 'auditor'
  onLogout?: () => void
}

export function CommandPalette({ open, onClose, sections, accent = 'company', onLogout }: CommandPaletteProps) {
  const navigate = useNavigate()
  const { theme, toggle } = useTheme()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const commands = useMemo<Command[]>(() => {
    const navCmds: Command[] = sections.flatMap((s) =>
      s.items.map((item) => ({
        id: `nav:${item.to}`,
        label: item.label,
        hint: s.title ?? 'Navigate',
        icon: item.icon,
        run: () => navigate(item.to),
      })),
    )
    const actions: Command[] = [
      {
        id: 'theme',
        label: theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode',
        hint: 'Appearance',
        icon: theme === 'dark' ? Sun : Moon,
        run: toggle,
      },
    ]
    if (onLogout) {
      actions.push({ id: 'logout', label: 'Log out', hint: 'Session', icon: LogOut, run: onLogout })
    }
    return [...navCmds, ...actions]
  }, [sections, navigate, theme, toggle, onLogout])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return commands
    return commands.filter((c) => c.label.toLowerCase().includes(q) || c.hint?.toLowerCase().includes(q))
  }, [commands, query])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
      setTimeout(() => inputRef.current?.focus(), 20)
    }
  }, [open])

  useEffect(() => setActive(0), [query])

  const run = (cmd?: Command) => {
    if (!cmd) return
    onClose()
    cmd.run()
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(filtered.length - 1, a + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(0, a - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      run(filtered[active])
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[14vh] backdrop-blur-sm"
          onMouseDown={onClose}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <motion.div
            onMouseDown={(e) => e.stopPropagation()}
            className="w-full max-w-xl overflow-hidden rounded-card border border-border bg-bg-surface shadow-modal"
            initial={{ opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 4 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="flex items-center gap-3 border-b border-border px-4">
              <Search className="h-4 w-4 shrink-0 text-text-muted" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Search pages and actions…"
                className="h-14 w-full bg-transparent text-md text-text-primary placeholder:text-text-muted focus:outline-none"
              />
              <kbd className="hidden shrink-0 rounded border border-border bg-bg-raised px-1.5 py-0.5 font-mono text-xs text-text-muted sm:block">
                ESC
              </kbd>
            </div>
            <div className="max-h-[52vh] overflow-y-auto p-2">
              {filtered.length === 0 ? (
                <p className="px-3 py-8 text-center text-sm text-text-muted">No matches for “{query}”</p>
              ) : (
                filtered.map((cmd, i) => {
                  const Icon = cmd.icon
                  return (
                    <button
                      key={cmd.id}
                      onMouseEnter={() => setActive(i)}
                      onClick={() => run(cmd)}
                      className={cn(
                        'flex w-full items-center gap-3 rounded-btn px-3 py-2.5 text-left text-sm transition-colors',
                        i === active
                          ? accent === 'auditor'
                            ? 'bg-auditor-subtle text-auditor'
                            : 'bg-accent-subtle text-accent'
                          : 'text-text-primary hover:bg-bg-raised',
                      )}
                    >
                      {Icon && <Icon className="h-[18px] w-[18px] shrink-0" />}
                      <span className="flex-1 font-medium">{cmd.label}</span>
                      <span className="text-xs text-text-muted">{cmd.hint}</span>
                      {i === active && <CornerDownLeft className="h-3.5 w-3.5 shrink-0 opacity-70" />}
                    </button>
                  )
                })
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
