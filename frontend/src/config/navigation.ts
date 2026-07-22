import {
  LayoutDashboard,
  Users,
  Target,
  Laptop,
  TrendingUp,
  SlidersHorizontal,
  Archive,
  ClipboardCheck,
  ScrollText,
  ShieldCheck,
  Bell,
  History,
  FolderSearch,
  Building2,
} from 'lucide-react'
import type { NavSection } from '@/components/ui/Sidebar'

/**
 * Sidebar navigation, built from the actual backend modules discovered in
 * app/routers (not assumed). Company and auditor get entirely separate trees.
 */
export const companyNav: NavSection[] = [
  {
    items: [
      { label: 'Dashboard', to: '/app', icon: LayoutDashboard, moduleId: 'dashboard' },
      { label: 'Directory', to: '/app/users', icon: Users }, // Users directory is not a module
    ],
  },
  {
    title: 'Apps',
    items: [
      { label: 'DocVault', to: '/app/docvault', icon: Archive, moduleId: 'docvault' },
      { label: 'AuditEase', to: '/app/auditease', icon: ShieldCheck, moduleId: 'auditease' },
    ],
  },
  {
    title: 'Operations',
    items: [
      { label: 'Assets', to: '/app/assets', icon: Laptop, moduleId: 'assets' },
      { label: 'Sales', to: '/app/sales', icon: TrendingUp, moduleId: 'sales' },
      { label: 'Custom Fields', to: '/app/custom-fields', icon: SlidersHorizontal },
      { label: 'ROC Compliance', to: '/app/compliance/roc', icon: ClipboardCheck, moduleId: 'compliance' },
      { label: 'SecretarialEase', to: '/app/compliance/secretarial', icon: ScrollText, moduleId: 'compliance' },
      { label: 'KRA & Appraisals', to: '/app/kra', icon: Target, moduleId: 'kra' },
    ],
  },
  {
    title: 'System',
    items: [
      { label: 'Company Profile', to: '/app/settings/profile', icon: Building2 },
      { label: 'Notifications', to: '/app/notifications', icon: Bell, moduleId: 'notifications' },
      { label: 'Activity Log', to: '/app/activity', icon: History, moduleId: 'activity' },
    ],
  },
]

export const auditorNav: NavSection[] = [
  {
    items: [{ label: 'Engagements', to: '/auditor/app', icon: FolderSearch }],
  },
]
