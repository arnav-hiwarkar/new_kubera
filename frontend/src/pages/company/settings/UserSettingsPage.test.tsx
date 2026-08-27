import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { UserSettingsPage } from './UserSettingsPage'
import { usersApi } from '@/api/endpoints/users'

let mockProfile: any = {
  id: 'user-1',
  email: 'test@example.com',
  full_name: 'Test User',
  role: 'employee',
  department: 'Engineering',
  designation: 'Staff Engineer',
  can_change_password: true,
  has_avatar: false,
  password_changed_at: null,
  avatar_updated_at: null,
}

vi.mock('@/auth/company', () => ({
  useCompanyAuth: () => ({
    profile: mockProfile,
  }),
}))

vi.mock('@/api/endpoints/users', () => ({
  usersApi: {
    me: vi.fn(),
    changePassword: vi.fn(),
    uploadAvatar: vi.fn(),
    getAvatarBlob: vi.fn().mockRejectedValue(new Error('No avatar')),
  },
}))

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockProfile = {
    id: 'user-1',
    email: 'test@example.com',
    full_name: 'Test User',
    role: 'employee',
    department: 'Engineering',
    designation: 'Staff Engineer',
    can_change_password: true,
    has_avatar: false,
    password_changed_at: null,
    avatar_updated_at: null,
  }
})

describe('UserSettingsPage', () => {
  it('renders account details and profile picture section', () => {
    wrap(<UserSettingsPage />)

    expect(screen.getByText('User Settings')).toBeInTheDocument()
    expect(screen.getByText('Test User')).toBeInTheDocument()
    expect(screen.getByText('test@example.com')).toBeInTheDocument()
    expect(screen.getByText('Staff Engineer • Engineering')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Upload New Photo/i })).toBeInTheDocument()
    expect(screen.getByText('Change Password')).toBeInTheDocument()
  })

  it('hides Change Password card when can_change_password is false', () => {
    mockProfile = {
      ...mockProfile,
      can_change_password: false,
    }

    wrap(<UserSettingsPage />)

    expect(screen.getByText('Account Details')).toBeInTheDocument()
    expect(screen.getByText('Profile Picture')).toBeInTheDocument()
    expect(screen.queryByText('Change Password')).not.toBeInTheDocument()
  })

  it('renders 30-day cooldown banner when password was recently changed', () => {
    const recentDate = new Date()
    recentDate.setDate(recentDate.getDate() - 5) // 5 days ago

    mockProfile = {
      ...mockProfile,
      password_changed_at: recentDate.toISOString(),
    }

    wrap(<UserSettingsPage />)

    expect(screen.getByText(/30-Day Cooldown Active/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Update Password' })).toBeDisabled()
  })

  it('validates password requirements in real time and submits valid password change', async () => {
    const user = userEvent.setup()
    vi.mocked(usersApi.changePassword).mockResolvedValue({ success: true, message: 'Success' })

    wrap(<UserSettingsPage />)

    const oldInput = screen.getByLabelText(/Current Password/i)
    const newInput = screen.getByLabelText(/^New Password/i)
    const confirmInput = screen.getByLabelText(/Confirm New Password/i)
    const submitBtn = screen.getByRole('button', { name: 'Update Password' })

    expect(submitBtn).toBeDisabled()

    // Fill current password
    await user.type(oldInput, 'OldPass123!')
    expect(submitBtn).toBeDisabled()

    // Type weak new password
    await user.type(newInput, 'weak')
    expect(submitBtn).toBeDisabled()

    // Type strong new password
    await user.clear(newInput)
    await user.type(newInput, 'StrongPass@2026')
    expect(submitBtn).toBeDisabled() // confirm is empty

    // Fill matching confirm password
    await user.type(confirmInput, 'StrongPass@2026')
    expect(submitBtn).toBeEnabled()

    // Click submit
    await user.click(submitBtn)
    expect(usersApi.changePassword).toHaveBeenCalledWith({
      old_password: 'OldPass123!',
      new_password: 'StrongPass@2026',
      confirm_password: 'StrongPass@2026',
    })
  })
})
