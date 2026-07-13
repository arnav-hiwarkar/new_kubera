import type { NavSection } from '@/components/ui/Sidebar'

/**
 * Sidebar navigation, built from the actual backend modules discovered in
 * app/routers (not assumed). Company and auditor get entirely separate trees.
 */
export const companyNav: NavSection[] = [
  {
    items: [{ label: 'Dashboard', to: '/app', glyph: '▤' }],
  },
  {
    title: 'Workforce',
    items: [
      { label: 'Directory', to: '/app/users', glyph: '👥' },
      { label: 'KRA & Appraisals', to: '/app/kra', glyph: '🎯' },
    ],
  },
  {
    title: 'Operations',
    items: [
      { label: 'Assets', to: '/app/assets', glyph: '💻' },
      { label: 'Sales', to: '/app/sales', glyph: '📈' },
      { label: 'Custom Fields', to: '/app/custom-fields', glyph: '⚙' },
    ],
  },
  {
    title: 'Documents & Compliance',
    items: [
      { label: 'DocVault', to: '/app/docvault', glyph: '🗄' },
      { label: 'ROC Compliance', to: '/app/compliance/roc', glyph: '📋' },
      { label: 'SecretarialEase', to: '/app/compliance/secretarial', glyph: '📑' },
    ],
  },
  {
    title: 'Audit',
    items: [{ label: 'AuditEase', to: '/app/auditease', glyph: '🔍' }],
  },
  {
    title: 'System',
    items: [
      { label: 'Notifications', to: '/app/notifications', glyph: '🔔' },
      { label: 'Activity Log', to: '/app/activity', glyph: '🕑' },
    ],
  },
]

export const auditorNav: NavSection[] = [
  {
    items: [{ label: 'Engagements', to: '/auditor/app', glyph: '🔍' }],
  },
]
