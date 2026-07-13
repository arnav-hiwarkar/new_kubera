import { createBrowserRouter, Navigate, type RouteObject } from 'react-router-dom'
import { companyRoutes } from './company.routes'
import { auditorRoutes } from './auditor.routes'

/** The full route table. Exported so tests can mount it with a memory router. */
export const appRoutes: RouteObject[] = [
  { path: '/', element: <Navigate to="/app" replace /> },
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
