import { Outlet, useNavigate } from 'react-router-dom'
import { Sidebar } from '@/components/ui/Sidebar'
import { TopBar } from '@/components/ui/TopBar'
import { companyNav } from '@/config/navigation'
import { useCompanyAuth } from '@/auth/company'

export function CompanyShell() {
  const { profile, signOut } = useCompanyAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar brand="Kubera" sections={companyNav} accent="company" />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar
          name={profile?.full_name ?? profile?.email ?? 'User'}
          subtitle={profile?.role}
          onLogout={handleLogout}
          accent="company"
        />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
