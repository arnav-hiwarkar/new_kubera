import { Outlet, useNavigate } from 'react-router-dom'
import { Sidebar } from '@/components/ui/Sidebar'
import { TopBar } from '@/components/ui/TopBar'
import { auditorNav } from '@/config/navigation'
import { useAuditorAuth } from '@/auth/auditor'

export function AuditorShell() {
  const { profile, signOut } = useAuditorAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    signOut()
    navigate('/auditor/login', { replace: true })
  }

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar brand="Kubera Audit" sections={auditorNav} accent="auditor" />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar
          name={profile?.name ?? profile?.email ?? 'Auditor'}
          subtitle="Auditor"
          onLogout={handleLogout}
          accent="auditor"
        />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
