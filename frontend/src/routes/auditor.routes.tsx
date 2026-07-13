import type { RouteObject } from 'react-router-dom'
import { Navigate, Outlet } from 'react-router-dom'
import { AuditorAuthProvider, AuditorGuard } from '@/auth/auditor'
import { AuditorShell } from '@/layouts/AuditorShell'
import { AuditorLogin } from '@/pages/auditor/AuditorLogin'
import { AuditorRegister } from '@/pages/auditor/AuditorRegister'
import { AuditorEngagements } from '@/pages/auditor/AuditorEngagements'

function AuditorAuthLayout() {
  return (
    <AuditorAuthProvider>
      <Outlet />
    </AuditorAuthProvider>
  )
}

/**
 * Auditor identity route tree, entirely under `/auditor`. Guarded by AuditorGuard,
 * which authenticates ONLY against the auditor token namespace. Mirrors the
 * backend, where the auditor identity can reach only `/api/v1/auditor/*`.
 */
export const auditorRoutes: RouteObject = {
  path: 'auditor',
  element: <AuditorAuthLayout />,
  children: [
    { path: 'login', element: <AuditorLogin /> },
    { path: 'register', element: <AuditorRegister /> },
    {
      path: 'app',
      element: <AuditorGuard />,
      children: [
        {
          element: <AuditorShell />,
          children: [
            { index: true, element: <AuditorEngagements /> },
            { path: '*', element: <Navigate to="/auditor/app" replace /> },
          ],
        },
      ],
    },
  ],
}
