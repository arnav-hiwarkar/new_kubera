import type { NavSection } from '@/components/ui/Sidebar'

/**
 * Sidebar navigation, built from the actual backend modules discovered in
 * app/routers (not assumed). Company and auditor get entirely separate trees.
 */
export const companyNav: NavSection[] = [
  {
    items: [{ label: 'Dashboard', to: '/app', glyph: '▤', moduleId: 'dashboard' }],
  },
  {
    title: 'Workforce',
    items: [
      { label: 'Directory', to: '/app/users', glyph: '👥' }, // Users directory is not a module
      { label: 'KRA & Appraisals', to: '/app/kra', glyph: '🎯', moduleId: 'kra' },
    ],
  },
  {
    title: 'Operations',
    items: [
      { label: 'Assets', to: '/app/assets', glyph: '💻', moduleId: 'assets' },
      { label: 'Sales', to: '/app/sales', glyph: '📈', moduleId: 'sales' },
      { label: 'Custom Fields', to: '/app/custom-fields', glyph: '⚙' },
    ],
  },
  {
    title: 'Documents & Compliance',
    items: [
      { label: 'DocVault', to: '/app/docvault', glyph: '🗄', moduleId: 'docvault' },
      { label: 'ROC Compliance', to: '/app/compliance/roc', glyph: '📋', moduleId: 'compliance' },
      { label: 'SecretarialEase', to: '/app/compliance/secretarial', glyph: '📑', moduleId: 'compliance' },
    ],
  },
  {
    title: 'Audit',
    items: [{ label: 'AuditEase', to: '/app/auditease', glyph: '🔍', moduleId: 'auditease' }],
  },
  {
    title: 'System',
    items: [
      { label: 'Notifications', to: '/app/notifications', glyph: '🔔', moduleId: 'notifications' },
      { label: 'Activity Log', to: '/app/activity', glyph: '🕑', moduleId: 'activity' },
    ],
  },
]

export const auditorNav: NavSection[] = [
  {
    items: [{ label: 'Engagements', to: '/auditor/app', glyph: '🔍' }],
  },
]
