import type { RouteObject } from 'react-router-dom'
import { Navigate, Outlet } from 'react-router-dom'
import { CompanyAuthProvider, CompanyGuard } from '@/auth/company'
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
import { ModulePlaceholder } from '@/pages/ModulePlaceholder'

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
            { index: true, element: <Dashboard /> },
            { path: 'users', element: <UsersDirectory /> },
            { path: 'kra', element: <KraPage /> },
            { path: 'assets', element: <AssetsPage /> },
            { path: 'sales', element: <SalesPage /> },
            { path: 'custom-fields', element: <CustomFieldsPage /> },
            { path: 'docvault', element: <DocVaultPage /> },
            {
              path: 'compliance/roc',
              element: (
                <ModulePlaceholder
                  title="ROC Compliance"
                  description="Registrar of Companies document types and meeting records"
                  endpoints={['/api/v1/roc/document-types', '/api/v1/roc/meeting-records']}
                />
              ),
            },
            {
              path: 'compliance/secretarial',
              element: (
                <ModulePlaceholder
                  title="SecretarialEase"
                  description="Secretarial compliance document types and meeting records"
                  endpoints={[
                    '/api/v1/secretarial/document-types',
                    '/api/v1/secretarial/meeting-records',
                  ]}
                />
              ),
            },
            {
              path: 'auditease',
              children: [
                { index: true, element: <EngagementsPage /> },
                { path: ':engagementId', element: <EngagementWorkspace /> },
              ],
            },
            {
              path: 'notifications',
              element: (
                <ModulePlaceholder
                  title="Notifications"
                  description="Company notifications"
                  endpoints={['/api/v1/notifications']}
                />
              ),
            },
            {
              path: 'activity',
              element: (
                <ModulePlaceholder
                  title="Activity Log"
                  description="Audit trail of company actions"
                  endpoints={['/api/v1/activity-log']}
                />
              ),
            },
            { path: '*', element: <Navigate to="/app" replace /> },
          ],
        },
      ],
    },
  ],
}
