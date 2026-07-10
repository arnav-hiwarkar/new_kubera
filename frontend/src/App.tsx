import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

import { AppAuthProvider } from '@/contexts/AppAuthContext';
import { AuditorAuthProvider } from '@/contexts/AuditorAuthContext';

import { AppGuard } from '@/components/guards/AppGuard';
import { AdminGuard } from '@/components/guards/AdminGuard';
import { AuditorGuard } from '@/components/guards/AuditorGuard';

import { AppLayout } from '@/components/layout/AppLayout';
import { AuditorLayout } from '@/components/layout/AuditorLayout';
import { Placeholder } from '@/components/Placeholder';

import CompanyLoginPage from '@/pages/app/LoginPage';
import AuditorLoginPage from '@/pages/auditor/LoginPage';
import AuditorRegisterPage from '@/pages/auditor/RegisterPage';
import DocVaultPage from '@/pages/app/docvault/DocVaultPage';

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppAuthProvider>
          <AuditorAuthProvider>
            <Routes>
              {/* Redirect root to company login */}
              <Route path="/" element={<Navigate to="/app/login" replace />} />

              {/* Company Portal */}
              <Route path="/app/login" element={<CompanyLoginPage />} />
              <Route path="/app" element={<AppGuard />}>
                <Route element={<AppLayout />}>
                  <Route index element={<Placeholder title="Dashboard" />} />
                  <Route path="docvault/*" element={<DocVaultPage />} />
                  <Route path="auditease/*" element={<Placeholder title="AuditEase" />} />
                  <Route path="secretarial/*" element={<Placeholder title="Secretarial" />} />
                  <Route path="roc/*" element={<Placeholder title="ROC Compliance" />} />
                  <Route path="assets/*" element={<Placeholder title="Asset Management" />} />
                  <Route path="sales/*" element={<Placeholder title="Sales Tracking" />} />
                  <Route path="kra/*" element={<Placeholder title="KRA & Appraisal" />} />

                  {/* Admin Only */}
                  <Route element={<AdminGuard />}>
                    <Route path="users" element={<Placeholder title="User Management" />} />
                    <Route path="settings/*" element={<Placeholder title="Settings" />} />
                  </Route>
                </Route>
              </Route>

              {/* Auditor Portal */}
              <Route path="/auditor/login" element={<AuditorLoginPage />} />
              <Route path="/auditor/register" element={<AuditorRegisterPage />} />
              <Route path="/auditor" element={<AuditorGuard />}>
                <Route element={<AuditorLayout />}>
                  <Route index element={<Placeholder title="Auditor Dashboard" />} />
                  <Route path="engagements/*" element={<Placeholder title="Engagements" />} />
                </Route>
              </Route>

              {/* Catch all */}
              <Route path="*" element={<Navigate to="/app/login" replace />} />
            </Routes>
            <Toaster position="top-right" theme="dark" />
          </AuditorAuthProvider>
        </AppAuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
