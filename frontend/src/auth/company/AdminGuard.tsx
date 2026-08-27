import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useCompanyAuth } from '@/auth/company'

interface AdminGuardProps {
  children: ReactNode
}

export function AdminGuard({ children }: AdminGuardProps) {
  const { profile } = useCompanyAuth()
  if (profile?.role !== 'admin') {
    return <Navigate to="/app" replace />
  }
  return <>{children}</>
}
