import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/components/ui/Toast'
import { ApiContractError } from '@/api/contracts/trialBalance'
import { EngagementWorkspace } from './EngagementWorkspace'
import { AuditorEngagementWorkspace } from '@/pages/auditor/AuditorEngagementWorkspace'

const contractError = new ApiContractError('TrialBalanceViewResponse/v2')
const failedTrialBalance = {
  data: undefined,
  isLoading: false,
  isError: true,
  error: contractError,
  refetch: vi.fn(),
}

vi.mock('@/api/hooks/auditease', () => ({
  useEngagement: () => ({
    data: {
      id: 'eng-1',
      period_label: 'FY 2025-26',
      status: 'active',
      auditors: [],
    },
    isLoading: false,
  }),
  useCompanyTrialBalance: () => failedTrialBalance,
  useCloseEngagement: () => ({ mutateAsync: vi.fn() }),
  useSetSignConvention: () => ({ mutate: vi.fn(), isPending: false }),
  useListRequirements: () => ({ data: [] }),
  useListQueries: () => ({ data: [] }),
  useListEntries: () => ({ data: [] }),
  useEngagementAuditors: () => ({ data: [], isLoading: false }),
  useInviteEngagementAuditor: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateAuditorAccess: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoveEngagementAuditor: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAuditorActivity: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: { role: 'admin' } }),
}))

vi.mock('@/api/hooks/auditorEngagements', () => ({
  useAuditorEngagements: () => ({
    data: [{ id: 'eng-1', period_label: 'FY 2025-26', status: 'active' }],
    isLoading: false,
  }),
  useAuditorTrialBalance: () => failedTrialBalance,
  useAuditorListRequirements: () => ({ data: [] }),
  useAuditorListQueries: () => ({ data: [] }),
  useAuditorListEntries: () => ({ data: [] }),
}))

function renderWorkspace(kind: 'company' | 'auditor') {
  const path = kind === 'company' ? '/app/auditease/eng-1' : '/auditor/app/eng-1'
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <Routes>
          <Route
            path={kind === 'company' ? '/app/auditease/:engagementId' : '/auditor/app/:engagementId'}
            element={kind === 'company' ? <EngagementWorkspace /> : <AuditorEngagementWorkspace />}
          />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('engagement trial-balance contract recovery', () => {
  it('keeps the company engagement and its navigation accessible', () => {
    renderWorkspace('company')
    expect(screen.getByRole('heading', { name: 'FY 2025-26' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AuditEase was updated' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Requirements/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reports' })).toBeInTheDocument()
  })

  it('keeps the auditor engagement and its navigation accessible', () => {
    renderWorkspace('auditor')
    expect(screen.getByRole('heading', { name: 'FY 2025-26' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AuditEase was updated' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Entries/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Queries/ })).toBeInTheDocument()
  })
})
