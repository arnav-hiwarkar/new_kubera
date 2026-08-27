import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { AdminGuard } from './AdminGuard'
import * as auth from '@/auth/company'

vi.mock('@/auth/company', () => ({
  useCompanyAuth: vi.fn(),
}))

describe('AdminGuard', () => {
  it('renders children when user is admin', () => {
    vi.mocked(auth.useCompanyAuth).mockReturnValue({
      profile: { role: 'admin' },
    } as any)

    render(
      <MemoryRouter initialEntries={['/app/users']}>
        <Routes>
          <Route path="/app/users" element={<AdminGuard><div>Admin Secret</div></AdminGuard>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText('Admin Secret')).toBeInTheDocument()
  })

  it('redirects to /app when user is employee', () => {
    vi.mocked(auth.useCompanyAuth).mockReturnValue({
      profile: { role: 'employee' },
    } as any)

    render(
      <MemoryRouter initialEntries={['/app/users']}>
        <Routes>
          <Route path="/app/users" element={<AdminGuard><div>Admin Secret</div></AdminGuard>} />
          <Route path="/app" element={<div>Dashboard Home</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.queryByText('Admin Secret')).not.toBeInTheDocument()
    expect(screen.getByText('Dashboard Home')).toBeInTheDocument()
  })
})
