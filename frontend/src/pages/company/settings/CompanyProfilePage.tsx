import { PageHeader, FullPageSpinner } from '@/components/ui'
import { useCompanyProfile } from '@/api/hooks/companyProfile'
import { useCompanyAuth } from '@/auth/company'
import { CompanyProfileForm } from '@/pages/company/CompanyProfileForm'
import { CompanySmtpCard } from '@/pages/company/settings/CompanySmtpCard'

/** Settings section: view + edit the company profile and outbound SMTP settings (admin edits, others read-only). */
export function CompanyProfilePage() {
  const { data: profile, isLoading } = useCompanyProfile()
  const { profile: user } = useCompanyAuth()
  const canEdit = user?.role === 'admin'

  if (isLoading || !profile) return <FullPageSpinner />

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Company Profile" description="Your registered company details and mail settings" />
      <div className="rounded-card border border-border bg-bg-surface p-6 sm:p-8">
        <CompanyProfileForm profile={profile} mode="settings" />
      </div>
      <CompanySmtpCard canEdit={canEdit} />
    </div>
  )
}
