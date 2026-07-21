import { Outlet, useNavigate } from 'react-router-dom'
import { Sidebar } from '@/components/ui/Sidebar'
import { TopBar } from '@/components/ui/TopBar'
import { PageTransition } from '@/layouts/PageTransition'
import { companyNav } from '@/config/navigation'
import { useCompanyAuth } from '@/auth/company'
import { useCompanyBranding } from '@/api/hooks/companyProfile'
import { hasModuleAccess, type ModuleId } from '@/auth/company/ModuleGuard'

export function CompanyShell() {
  const { profile, signOut } = useCompanyAuth()
  const { name: orgName, logoUrl: orgLogoUrl } = useCompanyBranding()
  const navigate = useNavigate()

  const handleLogout = () => {
    signOut()
    navigate('/login', { replace: true })
  }

  const accessibleNav = companyNav
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        const anyItem = item as any
        if (!anyItem.moduleId) return true // public item like directory or custom-fields
        return hasModuleAccess(profile, anyItem.moduleId as ModuleId)
      }),
    }))
    .filter((section) => section.items.length > 0)

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar
        brand="Kubera"
        tagline="Compliance OS"
        sections={accessibleNav}
        accent="company"
        orgName={orgName}
        orgLogoUrl={orgLogoUrl}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar
          name={profile?.full_name ?? profile?.email ?? 'User'}
          subtitle={profile?.role}
          onLogout={handleLogout}
          accent="company"
          sections={accessibleNav}
        />
        <main className="flex-1 overflow-y-auto p-6 lg:p-8">
          <PageTransition>
            <Outlet />
          </PageTransition>
        </main>
      </div>
    </div>
  )
}
