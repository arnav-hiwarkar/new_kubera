import React from 'react'
import { Navigate } from 'react-router-dom'
import { useCompanyAuth } from './index'

export const MODULE_IDS = [
  'dashboard',
  'docvault',
  'sales',
  'assets',
  'kra',
  'auditease',
  'compliance',
  'notifications',
  'activity',
] as const

export type ModuleId = typeof MODULE_IDS[number]

export function hasModuleAccess(profile: any, moduleId: ModuleId): boolean {
  if (!profile) return false
  if (profile.role === 'admin') return true
  // Cast to ensure we can read accessible_modules from the generated type
  const modules = (profile as any).accessible_modules || []
  return modules.includes(moduleId)
}

interface ModuleGuardProps {
  moduleId: ModuleId
  children: React.ReactNode
}

export function ModuleGuard({ moduleId, children }: ModuleGuardProps) {
  const { profile } = useCompanyAuth()
  
  if (!hasModuleAccess(profile, moduleId)) {
    return <Navigate to="/app" replace />
  }

  return <>{children}</>
}
