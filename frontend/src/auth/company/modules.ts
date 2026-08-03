export const MODULE_DEFINITIONS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'docvault', label: 'DocVault' },
  { id: 'sales', label: 'Sales' },
  { id: 'assets', label: 'Assets' },
  { id: 'kra', label: 'KRA & Appraisals' },
  { id: 'auditease', label: 'AuditEase' },
  { id: 'roc', label: 'ROC Compliance' },
  { id: 'secretarial', label: 'SecretarialEase' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'activity', label: 'Activity Log' },
] as const

export type ModuleId = (typeof MODULE_DEFINITIONS)[number]['id']

export const MODULE_IDS: readonly ModuleId[] = MODULE_DEFINITIONS.map(({ id }) => id)

interface ModuleAccessProfile {
  role?: string
  accessible_modules?: readonly string[]
}

export function hasModuleAccess(
  profile: ModuleAccessProfile | null | undefined,
  moduleId: ModuleId,
): boolean {
  if (!profile) return false
  if (profile.role === 'admin') return true
  return (profile.accessible_modules ?? []).includes(moduleId)
}
