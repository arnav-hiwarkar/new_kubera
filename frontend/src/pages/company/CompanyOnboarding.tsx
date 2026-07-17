import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { FullPageSpinner } from '@/components/ui'
import { useCompanyProfile } from '@/api/hooks/companyProfile'
import { useCompanyAuth } from '@/auth/company'
import { CompanyProfileForm } from '@/pages/company/CompanyProfileForm'

/**
 * First-login onboarding: a standalone full-page form (outside the app shell)
 * that the admin must complete before entering the workspace. On completion the
 * ProfileGate stops redirecting here.
 */
export function CompanyOnboarding() {
  const navigate = useNavigate()
  const { signOut } = useCompanyAuth()
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
        <button
          type="button"
          onClick={() => signOut()}
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
          Use a different account
        </button>
        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-display text-text-primary">
            Welcome to {profile.name}
          </h1>
          <p className="mt-1.5 text-base text-text-secondary">
            Let’s set up your company profile. All details are optional — fill in what you have now and complete the rest later from Settings.
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
