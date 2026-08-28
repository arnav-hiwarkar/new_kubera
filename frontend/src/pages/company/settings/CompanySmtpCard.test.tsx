import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CompanySmtpCard } from './CompanySmtpCard'
import { companySmtpApi } from '@/api/endpoints/companySmtp'

import { ToastProvider } from '@/components/ui'

vi.mock('@/api/endpoints/companySmtp', () => ({
  companySmtpApi: {
    get: vi.fn(),
    update: vi.fn(),
    verify: vi.fn(),
    reset: vi.fn(),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  )
}

describe('CompanySmtpCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders unconfigured state with system default badge', async () => {
    vi.mocked(companySmtpApi.get).mockResolvedValue({
      configured: false,
      host: null,
      port: 587,
      user: null,
      from_email: null,
      from_name: null,
      use_tls: true,
      use_ssl: false,
      is_active: true,
      has_password: false,
      last_tested_at: null,
    })

    wrap(<CompanySmtpCard canEdit={true} />)

    await waitFor(() => {
      expect(screen.getByText(/Outbound Email & Custom SMTP/i)).toBeInTheDocument()
      expect(screen.getByText(/Using System Default \(kubera@ethdc.in\)/i)).toBeInTheDocument()
    })
  })

  it('renders active custom SMTP configuration', async () => {
    vi.mocked(companySmtpApi.get).mockResolvedValue({
      configured: true,
      host: 'smtp.office365.com',
      port: 587,
      user: 'audit@acme.com',
      from_email: 'audit@acme.com',
      from_name: 'Acme Audit',
      use_tls: true,
      use_ssl: false,
      is_active: true,
      has_password: true,
      last_tested_at: '2026-08-28T12:00:00Z',
    })

    wrap(<CompanySmtpCard canEdit={true} />)

    await waitFor(() => {
      expect(screen.getByText(/Custom SMTP Active/i)).toBeInTheDocument()
      expect(screen.getByDisplayValue('smtp.office365.com')).toBeInTheDocument()
      expect(screen.getAllByDisplayValue('audit@acme.com')).toHaveLength(2)
      expect(screen.getByText(/Revert to Default Mail/i)).toBeInTheDocument()
    })
  })

  it('performs live test connection on click', async () => {
    const user = userEvent.setup()
    vi.mocked(companySmtpApi.get).mockResolvedValue({
      configured: true,
      host: 'smtp.office365.com',
      port: 587,
      user: 'audit@acme.com',
      from_email: 'audit@acme.com',
      from_name: 'Acme Audit',
      use_tls: true,
      use_ssl: false,
      is_active: true,
      has_password: true,
      last_tested_at: null,
    })
    vi.mocked(companySmtpApi.verify).mockResolvedValue({
      success: true,
      host: 'smtp.office365.com',
      port: 587,
      user: 'audit@acme.com',
      latency_ms: 120.4,
      message: 'Connected successfully',
    })

    wrap(<CompanySmtpCard canEdit={true} />)

    await waitFor(() => {
      expect(screen.getByText(/Test Connection/i)).toBeInTheDocument()
    })

    await user.click(screen.getByText(/Test Connection/i))

    await waitFor(() => {
      expect(companySmtpApi.verify).toHaveBeenCalled()
      expect(screen.getByText(/Verification Passed/i)).toBeInTheDocument()
    })
  })
})
