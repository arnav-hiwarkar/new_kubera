import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAppAuth } from '@/contexts/AppAuthContext';

export function AppGuard() {
  const { isAuthenticated } = useAppAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/app/login" state={{ returnTo: location.pathname }} replace />;
  }

  return <Outlet />;
}
