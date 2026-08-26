import { createBrowserRouter, Navigate, type RouteObject } from 'react-router-dom'
import { companyRoutes } from './company.routes'
import { auditorRoutes } from './auditor.routes'
import { LandingPage } from '@/pages/landing/LandingPage'
import { OwnerLeadsPage } from '@/pages/owner/OwnerLeadsPage'

/**
 * Dispatches root path based on hostname:
 * - If on `app.*` (e.g. app.kuberacompliance.com), navigates directly into the SaaS app (`/app`).
 * - Otherwise (e.g. kuberacompliance.com, localhost), renders the Marketing Landing Page.
 */
export function RootDispatcher() {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname.toLowerCase()
    if (host.startsWith('app.')) {
      return <Navigate to="/app" replace />
    }
  }
  return <LandingPage />
}

/** The full route table. Exported so tests can mount it with a memory router. */
export const appRoutes: RouteObject[] = [
  { path: '/', element: <RootDispatcher /> },
  { path: '/landing', element: <LandingPage /> },
  { path: '/internal/owner-vault', element: <OwnerLeadsPage /> },
  companyRoutes,
  auditorRoutes,
  { path: '*', element: <Navigate to="/app" replace /> },
]

/**
 * Top-level router. The two identity trees are siblings and never nest:
 *   - company: `/login` + `/app/*`  (CompanyAuthProvider + CompanyGuard)
 *   - auditor: `/auditor/*`         (AuditorAuthProvider + AuditorGuard)
 * Each subtree carries its own auth provider and guard, so there is no shared
 * routing layer through which one identity's session could reach the other's.
 */
export const router = createBrowserRouter(appRoutes)
