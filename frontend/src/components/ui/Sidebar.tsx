import { useEffect, useState, type ComponentType } from 'react'
import { NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { cn } from '@/lib/cn'

export interface NavItem {
  label: string
  to: string
  /** Lucide icon component for the item. */
  icon?: ComponentType<{ className?: string }>
  moduleId?: string
}

export interface NavSection {
  title?: string
  items: NavItem[]
}

export interface SidebarProps {
  brand: string
  sections: NavSection[]
  /** Switches the active-item accent between the two identities. */
  accent?: 'company' | 'auditor'
  /** Optional tagline under the brand (e.g. "Compliance OS"). */
  tagline?: string
  /** Tenant company name, shown at the bottom when no logo is uploaded. */
  orgName?: string
  /** Object-URL of the tenant company logo, shown at the bottom when present. */
  orgLogoUrl?: string | null
}

const STORAGE_KEY = 'kubera.sidebar.collapsed'

export function Sidebar({ brand, sections, accent = 'company', tagline, orgName, orgLogoUrl }: SidebarProps) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(STORAGE_KEY) === '1'
  })

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  const isAuditor = accent === 'auditor'
  const brandGrad = isAuditor
    ? 'from-auditor to-auditor-hover'
    : 'from-accent to-accent-active'

  return (
    <aside
      className={cn(
        'relative z-20 flex h-screen shrink-0 flex-col border-r border-border bg-bg-surface transition-[width] duration-300 ease-spring',
        collapsed ? 'w-sidebar-collapsed' : 'w-sidebar',
      )}
    >
      {/* Brand */}
      <div className={cn('flex h-topbar shrink-0 items-center gap-2.5 border-b border-border px-4', collapsed && 'justify-center px-0')}>
        <span
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-md font-bold text-white shadow-sm',
            brandGrad,
          )}
        >
          K
        </span>
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate text-md font-bold tracking-display text-text-primary">{brand}</p>
            {tagline && <p className="truncate text-xs text-text-muted">{tagline}</p>}
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2.5 py-3">
        {sections.map((section, i) => (
          <div key={i} className="mb-4">
            {section.title && !collapsed && (
              <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">
                {section.title}
              </p>
            )}
            {section.title && collapsed && i > 0 && <div className="mx-2 mb-2 border-t border-border" />}
            <ul className="flex flex-col gap-0.5">
              {section.items.map((item) => {
                const Icon = item.icon
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to.split('/').length <= 3}
                      title={collapsed ? item.label : undefined}
                      className={({ isActive }) =>
                        cn(
                          'group relative flex items-center gap-3 rounded-btn px-2.5 py-2 text-sm font-medium transition-colors',
                          collapsed && 'justify-center px-0',
                          isActive
                            ? isAuditor
                              ? 'text-auditor'
                              : 'text-accent'
                            : 'text-text-secondary hover:bg-bg-raised hover:text-text-primary',
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && (
                            <motion.span
                              layoutId={`nav-active-${accent}`}
                              className={cn(
                                'absolute inset-0 rounded-btn',
                                isAuditor ? 'bg-auditor-subtle' : 'bg-accent-subtle',
                              )}
                              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                            />
                          )}
                          {Icon && <Icon className="relative z-10 h-[18px] w-[18px] shrink-0" />}
                          {!collapsed && <span className="relative z-10 truncate">{item.label}</span>}
                        </>
                      )}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Tenant company branding: logo if uploaded, else the name. When collapsed,
          only a small logo is shown (nothing if there's no logo). */}
      {((!collapsed && !!orgName) || !!orgLogoUrl) && (
        <div className="shrink-0 border-t border-border p-2.5">
          {orgLogoUrl ? (
            <div className="flex items-center justify-center" title={orgName}>
              <img
                src={orgLogoUrl}
                alt={orgName ?? 'Company logo'}
                className={cn(
                  'object-contain',
                  collapsed ? 'h-8 w-8 rounded-md' : 'max-h-9 w-auto max-w-full',
                )}
              />
            </div>
          ) : (
            <p
              className="truncate px-1 text-sm font-semibold text-text-primary"
              title={orgName}
            >
              {orgName}
            </p>
          )}
        </div>
      )}

      {/* Collapse toggle */}
      <div className="shrink-0 border-t border-border p-2.5">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className={cn(
            'flex w-full items-center gap-3 rounded-btn px-2.5 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-bg-raised hover:text-text-primary',
            collapsed && 'justify-center px-0',
          )}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <PanelLeftOpen className="h-[18px] w-[18px]" /> : <PanelLeftClose className="h-[18px] w-[18px]" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  )
}
