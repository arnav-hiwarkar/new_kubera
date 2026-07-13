import type { RouteObject } from 'react-router-dom'
import { Navigate, Outlet } from 'react-router-dom'
import { CompanyAuthProvider, CompanyGuard } from '@/auth/company'
import { ModuleGuard } from '@/auth/company/ModuleGuard'
import { CompanyShell } from '@/layouts/CompanyShell'
import { CompanyLogin } from '@/pages/company/CompanyLogin'
import { Dashboard } from '@/pages/company/Dashboard'
import { UsersDirectory } from '@/pages/company/UsersDirectory'
import { DocVaultPage } from '@/pages/company/docvault/DocVaultPage'
import { KraPage } from '@/pages/company/kra/KraPage'
import { AssetsPage } from '@/pages/company/assets/AssetsPage'
import { SalesPage } from '@/pages/company/sales/SalesPage'
import { CustomFieldsPage } from '@/pages/company/customfields/CustomFieldsPage'
import { EngagementsPage } from '@/pages/company/auditease/EngagementsPage'
import { EngagementWorkspace } from '@/pages/company/auditease/EngagementWorkspace'
import { CompliancePage } from '@/pages/company/compliance/CompliancePage'
import { NotificationsPage } from '@/pages/company/notifications/NotificationsPage'
import { ActivityLogPage } from '@/pages/company/activity/ActivityLogPage'

/**
 * Company identity route tree. Everything under `/app` is wrapped by CompanyGuard,
 * which only authenticates against the company token namespace. The provider wraps
 * both the public login and the guarded area so the login page can call signIn.
 */
function CompanyAuthLayout() {
  return (
    <CompanyAuthProvider>
      <Outlet />
    </CompanyAuthProvider>
  )
}

export const companyRoutes: RouteObject = {
  element: <CompanyAuthLayout />,
  children: [
    { path: 'login', element: <CompanyLogin /> },
    {
      path: 'app',
      element: <CompanyGuard />,
      children: [
        {
          element: <CompanyShell />,
          children: [
            { index: true, element: <ModuleGuard moduleId="dashboard"><Dashboard /></ModuleGuard> },
            { path: 'users', element: <UsersDirectory /> },
            { path: 'kra', element: <ModuleGuard moduleId="kra"><KraPage /></ModuleGuard> },
            { path: 'assets', element: <ModuleGuard moduleId="assets"><AssetsPage /></ModuleGuard> },
            { path: 'sales', element: <ModuleGuard moduleId="sales"><SalesPage /></ModuleGuard> },
            { path: 'custom-fields', element: <CustomFieldsPage /> },
            { path: 'docvault', element: <ModuleGuard moduleId="docvault"><DocVaultPage /></ModuleGuard> },
            { path: 'compliance/roc', element: <ModuleGuard moduleId="compliance"><CompliancePage domain="roc" /></ModuleGuard> },
            { path: 'compliance/secretarial', element: <ModuleGuard moduleId="compliance"><CompliancePage domain="secretarial" /></ModuleGuard> },
            {
              path: 'auditease',
              element: <ModuleGuard moduleId="auditease"><Outlet /></ModuleGuard>,
              children: [
                { index: true, element: <EngagementsPage /> },
                { path: ':engagementId', element: <EngagementWorkspace /> },
              ],
            },
            {
              path: 'notifications',
              element: <ModuleGuard moduleId="notifications"><NotificationsPage /></ModuleGuard>,
            },
            {
              path: 'activity',
              element: <ModuleGuard moduleId="activity"><ActivityLogPage /></ModuleGuard>,
            },
            { path: '*', element: <Navigate to="/app" replace /> },
          ],
        },
      ],
    },
  ],
}
