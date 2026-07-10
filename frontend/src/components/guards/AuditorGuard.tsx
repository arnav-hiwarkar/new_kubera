import { Navigate, Outlet } from 'react-router-dom';
import { useAuditorAuth } from '@/contexts/AuditorAuthContext';

export function AuditorGuard() {
  const { isAuthenticated } = useAuditorAuth();

  if (!isAuthenticated) {
    return <Navigate to="/auditor/login" replace />;
  }

  return <Outlet />;
}
