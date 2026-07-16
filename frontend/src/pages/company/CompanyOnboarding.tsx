import { useNavigate } from 'react-router-dom'
import { FullPageSpinner } from '@/components/ui'
import { useCompanyProfile } from '@/api/hooks/companyProfile'
import { CompanyProfileForm } from '@/pages/company/CompanyProfileForm'

/**
 * First-login onboarding: a standalone full-page form (outside the app shell)
 * that the admin must complete before entering the workspace. On completion the
 * ProfileGate stops redirecting here.
 */
export function CompanyOnboarding() {
  const navigate = useNavigate()
  const { data: profile, isLoading } = useCompanyProfile()

  if (isLoading || !profile) return <FullPageSpinner />

  // Already complete — nothing to do here.
  if (profile.profile_completed) {
    navigate('/app', { replace: true })
    return <FullPageSpinner />
  }

  return (
    <div className="min-h-screen bg-bg-primary px-6 py-12">
      <div className="mx-auto w-full max-w-3xl">
        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-display text-text-primary">
            Welcome to {profile.name}
          </h1>
          <p className="mt-1.5 text-base text-text-secondary">
            Let’s set up your company profile. These details are required before you can use the workspace.
          </p>
        </div>
        <div className="rounded-card border border-border bg-bg-surface p-6 sm:p-8">
          <CompanyProfileForm
            profile={profile}
            mode="onboarding"
            onSaved={(updated) => {
              if (updated.profile_completed) navigate('/app', { replace: true })
            }}
          />
        </div>
      </div>
    </div>
  )
}
