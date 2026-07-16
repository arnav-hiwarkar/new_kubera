import { PageHeader, FullPageSpinner } from '@/components/ui'
import { useCompanyProfile } from '@/api/hooks/companyProfile'
import { CompanyProfileForm } from '@/pages/company/CompanyProfileForm'

/** Settings section: view + edit the company profile (admin edits, others read-only). */
export function CompanyProfilePage() {
  const { data: profile, isLoading } = useCompanyProfile()

  if (isLoading || !profile) return <FullPageSpinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Company Profile" description="Your registered company details" />
      <div className="rounded-card border border-border bg-bg-surface p-6 sm:p-8">
        <CompanyProfileForm profile={profile} mode="settings" />
      </div>
    </div>
  )
}
