import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { UsersDirectory } from './UsersDirectory'
import { usersApi } from '@/api/endpoints/users'
import { ApiError } from '@/api/http'
import type { UserResponse } from '@/api/types'

vi.mock('@/api/endpoints/users', () => ({
  usersApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), deactivate: vi.fn(), reactivate: vi.fn() },
}))

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({ profile: { id: 'admin-1', role: 'admin' } }),
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const base = {
  role: 'employee' as const,
  manager_id: null,
  designation: null,
  department: null,
  accessible_modules: [],
  company_id: 'c1',
  created_at: '2026-01-01T00:00:00Z',
}

const users: UserResponse[] = [
  { ...base, id: 'u1', email: 'active@co.com', full_name: 'Active Person', is_active: true, deleted_at: null },
  { ...base, id: 'u2', email: 'inactive@co.com', full_name: 'Inactive Person', is_active: false, deleted_at: null },
  { ...base, id: 'u3', email: 'gone@co.com', full_name: 'Deleted Person', is_active: false, deleted_at: '2026-02-02T00:00:00Z' },
]

beforeEach(() => vi.clearAllMocks())

describe('UsersDirectory', () => {
  it('renders Active / Inactive / Deleted statuses for every user', async () => {
    (usersApi.list as ReturnType<typeof vi.fn>).mockResolvedValue(users)
    wrap(<UsersDirectory />)

    expect(await screen.findByText('Active Person')).toBeInTheDocument()
    // A soft-deleted user is still listed (regression: they used to vanish).
    expect(screen.getByText('Deleted Person')).toBeInTheDocument()
    expect(screen.getByText('Inactive Person')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('Inactive')).toBeInTheDocument()
    expect(screen.getByText('Deleted')).toBeInTheDocument()
  })

  it('shows an error state (not an empty list) when the fetch fails', async () => {
    (usersApi.list as ReturnType<typeof vi.fn>).mockRejectedValue(new ApiError(500, 'boom'))
    wrap(<UsersDirectory />)

    expect(await screen.findByText(/Couldn't load users/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument()
    // Must NOT masquerade as an empty directory.
    expect(screen.queryByText('No users yet')).not.toBeInTheDocument()
  })
})
