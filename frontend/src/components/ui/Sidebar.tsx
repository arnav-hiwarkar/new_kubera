import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/cn'

export interface NavItem {
  label: string
  to: string
  /** Optional single-char / emoji glyph placeholder for the icon slot. */
  glyph?: string
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
}

export function Sidebar({ brand, sections, accent = 'company' }: SidebarProps) {
  const activeAccent =
    accent === 'auditor'
      ? 'bg-auditor-subtle text-auditor'
      : 'bg-accent-subtle text-accent'

  return (
    <aside className="flex h-screen w-sidebar shrink-0 flex-col border-r border-border bg-bg-surface">
      <div className="flex h-topbar shrink-0 items-center gap-2 border-b border-border px-4">
        <span
          className={cn(
            'flex h-6 w-6 items-center justify-center rounded text-xs font-bold text-white',
            accent === 'auditor' ? 'bg-auditor' : 'bg-accent',
          )}
        >
          K
        </span>
        <span className="text-md font-semibold text-text-primary">{brand}</span>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {sections.map((section, i) => (
          <div key={i} className="mb-4">
            {section.title && (
              <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-text-muted">
                {section.title}
              </p>
            )}
            <ul className="flex flex-col gap-0.5">
              {section.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to.split('/').length <= 3}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2 rounded-btn px-2 py-1.5 text-sm font-medium transition-colors',
                        isActive
                          ? activeAccent
                          : 'text-text-secondary hover:bg-bg-raised hover:text-text-primary',
                      )
                    }
                  >
                    {item.glyph && <span className="w-4 text-center">{item.glyph}</span>}
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  )
}
