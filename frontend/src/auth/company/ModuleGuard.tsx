import React from 'react'
import { Navigate } from 'react-router-dom'
import { useCompanyAuth } from './index'
import { hasModuleAccess, type ModuleId } from './modules'

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
