import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/cn'

export interface TabItem {
  id: string
  label: string
  /** Optional count pill (e.g. number of items). */
  count?: number
  icon?: ReactNode
}

export interface TabsProps {
  tabs: TabItem[]
  value: string
  onChange: (id: string) => void
  /** Drives the active-indicator color to match the identity. */
  accent?: 'company' | 'auditor'
  /** Unique id so multiple tab bars on one page don't share the indicator. */
  layoutGroup?: string
  className?: string
}

/**
 * Shared tab bar with a sliding underline indicator (framer-motion shared
 * layout). Replaces the hand-rolled `-mb-px border-b-2` snippets across pages.
 */
export function Tabs({ tabs, value, onChange, accent = 'company', layoutGroup = 'tabs', className }: TabsProps) {
  const activeText = accent === 'auditor' ? 'text-auditor' : 'text-accent'
  const activeBar = accent === 'auditor' ? 'bg-auditor' : 'bg-accent'

  return (
    <div className={cn('flex items-center gap-1 border-b border-border', className)}>
      {tabs.map((tab) => {
        const active = tab.id === value
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={cn(
              'relative flex items-center gap-2 px-3 py-2.5 text-sm font-medium transition-colors',
              active ? activeText : 'text-text-secondary hover:text-text-primary',
              '[&_svg]:h-4 [&_svg]:w-4',
            )}
          >
            {tab.icon}
            {tab.label}
            {typeof tab.count === 'number' && (
              <span
                className={cn(
                  'rounded-pill px-1.5 py-0.5 text-xs font-semibold tabular-nums',
                  active ? 'bg-accent-subtle text-accent' : 'bg-bg-raised text-text-muted',
                  accent === 'auditor' && active && 'bg-auditor-subtle text-auditor',
                )}
              >
                {tab.count}
              </span>
            )}
            {active && (
              <motion.span
                layoutId={`${layoutGroup}-indicator`}
                className={cn('absolute inset-x-2 -bottom-px h-0.5 rounded-full', activeBar)}
                transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}
