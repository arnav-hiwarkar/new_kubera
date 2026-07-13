import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '@/components/ui/Toast'
import { KraPage } from './KraPage'
import type { KRAResponse, UserResponse } from '@/api/types'
import { kraApi } from '@/api/endpoints/kra'
import { usersApi } from '@/api/endpoints/users'

const authState = vi.hoisted(() => ({
  profile: null as { id: string; role: string; full_name: string } | null,
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({
    profile: authState.profile,
    status: 'authenticated',
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}))
vi.mock('@/api/endpoints/kra', () => ({
  kraApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn() },
}))
vi.mock('@/api/endpoints/users', () => ({
  usersApi: { list: vi.fn().mockResolvedValue([]), myReports: vi.fn().mockResolvedValue([]) },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  )
}

function kra(over: Partial<KRAResponse>): KRAResponse {
  return {
    id: 'k1',
    company_id: 'co',
    title: 'Ship v1',
    description: 'Launch the product',
    weightage: 40,
    target_metric: null,
    cycle: 'FY25-Q1',
    status: 'draft',
    user_id: 'emp',
    manager_id: 'mgr',
    employee_self_rating: null,
    employee_comment: null,
    manager_rating: null,
    manager_comment: null,
    rejection_reason: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

function user(over: Partial<UserResponse>): UserResponse {
  return {
    id: 'emp',
    email: 'e@a.com',
    full_name: 'Emp',
    role: 'employee',
    manager_id: 'mgr',
    designation: null,
    department: null,
    is_active: true,
    company_id: 'co',
    created_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('KraPage — employee', () => {
  beforeEach(() => {
    authState.profile = { id: 'emp', role: 'employee', full_name: 'Emp' }
  })

  it('shows only My KRAs (no Team tab) and lists own KRAs', async () => {
    vi.mocked(kraApi.list).mockResolvedValue([kra({})])
    wrap(<KraPage />)
    expect(await screen.findByText('Ship v1')).toBeInTheDocument()
    expect(screen.getByText(/My KRAs/)).toBeInTheDocument()
    expect(screen.queryByText(/^Team/)).not.toBeInTheDocument()
  })

  it('opens a draft in the drawer with a Submit for approval action', async () => {
    vi.mocked(kraApi.list).mockResolvedValue([kra({})])
    const u = userEvent.setup()
    wrap(<KraPage />)
    await u.click(await screen.findByText('Ship v1'))
    expect(await screen.findByRole('button', { name: /Submit for approval/ })).toBeInTheDocument()
  })
})

describe('KraPage — manager', () => {
  beforeEach(() => {
    authState.profile = { id: 'mgr', role: 'manager', full_name: 'Mgr' }
    vi.mocked(usersApi.myReports).mockResolvedValue([user({ id: 'emp', full_name: 'Emp' })])
  })

  it('shows a Team tab and can act on a report’s pending KRA', async () => {
    vi.mocked(kraApi.list).mockResolvedValue([
      kra({ status: 'pending_approval', user_id: 'emp', manager_id: 'mgr' }),
    ])
    const u = userEvent.setup()
    wrap(<KraPage />)

    await u.click(await screen.findByText(/^Team/))
    // The report's KRA and their name are visible on the Team tab.
    expect(await screen.findByText('Ship v1')).toBeInTheDocument()
    expect(screen.getByText('Emp')).toBeInTheDocument()

    await u.click(screen.getByText('Ship v1'))
    expect(await screen.findByRole('button', { name: /Approve/ })).toBeInTheDocument()
  })
})
