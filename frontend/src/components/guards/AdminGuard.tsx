import { Navigate, Outlet } from 'react-router-dom';
import { useAppAuth } from '@/contexts/AppAuthContext';

export function AdminGuard() {
  const { role } = useAppAuth();

  if (role !== 'admin') {
    return <Navigate to="/app" replace />;
  }

  return <Outlet />;
}
