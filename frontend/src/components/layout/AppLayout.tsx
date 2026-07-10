import { NavLink, Outlet } from 'react-router-dom';
import { useAppAuth } from '@/contexts/AppAuthContext';
import {
  LayoutDashboard,
  FolderOpen,
  ClipboardCheck,
  Building2,
  FileText,
  Boxes,
  TrendingUp,
  Target,
  Settings,
  Users,
  LogOut,
  Menu
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

export function AppLayout() {
  const { user, role, logout } = useAppAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { name: 'Dashboard', path: '/app', icon: LayoutDashboard },
    { name: 'DocVault', path: '/app/docvault', icon: FolderOpen },
    { name: 'AuditEase', path: '/app/auditease', icon: ClipboardCheck },
    { name: 'Secretarial', path: '/app/secretarial', icon: Building2 },
    { name: 'ROC', path: '/app/roc', icon: FileText },
    { name: 'Assets', path: '/app/assets', icon: Boxes },
    { name: 'Sales', path: '/app/sales', icon: TrendingUp },
    { name: 'KRA', path: '/app/kra', icon: Target },
  ];

  const adminItems = [
    { name: 'Users', path: '/app/users', icon: Users },
    { name: 'Settings', path: '/app/settings', icon: Settings },
  ];

  const NavContent = () => (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center px-6">
        <h1 className="font-heading text-2xl tracking-wide text-primary">KUBERA</h1>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.name}
            to={item.path}
            end={item.path === '/app'}
            onClick={() => setMobileMenuOpen(false)}
            className={({ isActive }) =>
              cn(
                'group flex items-center rounded-md px-3 py-2 text-sm font-medium',
                isActive
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground ledger-strip-gold'
                  : 'text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground border-l-[3px] border-transparent'
              )
            }
          >
            <item.icon className="mr-3 h-5 w-5 flex-shrink-0" />
            {item.name}
          </NavLink>
        ))}

        {role === 'admin' && (
          <>
            <div className="mt-8 mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Admin
            </div>
            {adminItems.map((item) => (
              <NavLink
                key={item.name}
                to={item.path}
                onClick={() => setMobileMenuOpen(false)}
                className={({ isActive }) =>
                  cn(
                    'group flex items-center rounded-md px-3 py-2 text-sm font-medium',
                    isActive
                      ? 'bg-sidebar-accent text-sidebar-accent-foreground ledger-strip-gold'
                      : 'text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground border-l-[3px] border-transparent'
                  )
                }
              >
                <item.icon className="mr-3 h-5 w-5 flex-shrink-0" />
                {item.name}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      <div className="border-t border-sidebar-border p-4">
        <div className="flex items-center">
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm font-medium text-foreground">{user?.full_name}</p>
            <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={logout} className="ml-2 text-muted-foreground hover:text-foreground">
            <LogOut className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile sidebar overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/80 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-64 transform bg-sidebar transition-transform duration-200 ease-in-out lg:static lg:translate-x-0",
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <NavContent />
      </div>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile top bar */}
        <div className="flex h-14 items-center border-b border-border bg-sidebar px-4 lg:hidden">
          <Button variant="ghost" size="icon" onClick={() => setMobileMenuOpen(true)} className="mr-2">
            <Menu className="h-5 w-5" />
          </Button>
          <h1 className="font-heading text-xl tracking-wide text-primary">KUBERA</h1>
        </div>

        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
