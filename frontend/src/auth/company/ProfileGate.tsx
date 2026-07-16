import { Navigate, Outlet } from 'react-router-dom'
import { FullPageSpinner } from '@/components/ui'
import { useCompanyProfile } from '@/api/hooks/companyProfile'

/**
 * Blocks the app shell until the company profile is complete. While the profile
 * loads we show a spinner; if it is incomplete we redirect to onboarding. Placed
 * INSIDE the shell but around every real page (onboarding lives outside it, so
 * there is no redirect loop).
 */
export function ProfileGate() {
  const { data: profile, isLoading, isError } = useCompanyProfile()

  if (isLoading) return <FullPageSpinner />
  // On error, don't trap the user in a spinner — let the page render; the API
  // will surface auth issues through the normal 401 path.
  if (!isError && profile && !profile.profile_completed) {
    return <Navigate to="/app/onboarding" replace />
  }
  return <Outlet />
}
