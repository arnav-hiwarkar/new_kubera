import { Outlet, NavLink } from 'react-router-dom';
import { useAuditorAuth } from '@/contexts/AuditorAuthContext';
import { LogOut, Briefcase } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function AuditorLayout() {
  const { user, logout } = useAuditorAuth();

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-40 w-full border-b border-border bg-sidebar">
        <div className="flex h-16 items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <h1 className="font-heading text-2xl tracking-wide text-primary">KUBERA</h1>
            <span className="text-sm text-muted-foreground border-l border-sidebar-border pl-4">
              Auditor Portal
            </span>
          </div>
          <div className="flex flex-1 items-center gap-6 px-8">
            <NavLink 
              to="/auditor/engagements"
              className={({ isActive }) => cn(
                "flex items-center gap-2 text-sm font-medium transition-colors hover:text-primary",
                isActive ? "text-primary" : "text-muted-foreground"
              )}
            >
              <Briefcase className="h-4 w-4" />
              Engagements
            </NavLink>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium text-foreground">{user?.name}</p>
              <p className="text-xs text-muted-foreground">{user?.email}</p>
            </div>
            <Button variant="ghost" size="icon" onClick={logout} className="text-muted-foreground hover:text-foreground">
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </header>

      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
