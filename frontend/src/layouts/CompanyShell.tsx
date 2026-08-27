import { Outlet, useNavigate } from 'react-router-dom'
import { Sidebar } from '@/components/ui/Sidebar'
import { TopBar } from '@/components/ui/TopBar'
import { PageTransition } from '@/layouts/PageTransition'
import { companyNav } from '@/config/navigation'
import { useCompanyAuth } from '@/auth/company'
import { useCompanyBranding } from '@/api/hooks/companyProfile'
import { useUserAvatar } from '@/api/hooks/users'
import { hasModuleAccess } from '@/auth/company/modules'

export function CompanyShell() {
  const { profile, signOut } = useCompanyAuth()
  const { name: orgName, logoUrl: orgLogoUrl } = useCompanyBranding()
  const { avatarUrl } = useUserAvatar(profile?.id, profile?.has_avatar)
  const navigate = useNavigate()

  const handleLogout = () => {
    signOut()
    navigate('/login', { replace: true })
  }

  const accessibleNav = companyNav
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        if (item.adminOnly && profile?.role !== 'admin') return false
        if (!item.moduleId) return true // public item like custom-fields
        return hasModuleAccess(profile, item.moduleId)
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
          avatarUrl={avatarUrl}
          onLogout={handleLogout}
          onOpenSettings={() => navigate('/app/settings/user')}
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
