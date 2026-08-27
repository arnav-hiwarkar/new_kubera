import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserResponse } from '@/api/types'
import { UserModal } from './UserModal'

describe('UserModal module access', () => {
  it.each([
    ['ROC Compliance', 'roc', 'secretarial'],
    ['SecretarialEase', 'secretarial', 'roc'],
  ] as const)('submits %s independently', async (label, selected, excluded) => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <UserModal
        isOpen
        onClose={vi.fn()}
        onSave={onSave}
        initialData={null}
      />,
    )

    expect(screen.getByRole('checkbox', { name: 'ROC Compliance' })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'SecretarialEase' })).not.toBeChecked()
    expect(screen.queryByRole('checkbox', { name: 'Compliance' })).not.toBeInTheDocument()

    const dialog = screen.getByRole('dialog', { name: 'New User' })
    const inputs = within(dialog).getAllByRole('textbox')
    await user.type(inputs[0], 'New Employee')
    await user.type(inputs[1], 'new.employee@example.com')
    const password = dialog.querySelector<HTMLInputElement>('input[type="password"]')
    expect(password).not.toBeNull()
    await user.type(password!, 'pass1234')
    await user.click(screen.getByRole('checkbox', { name: label }))
    await user.click(screen.getByRole('button', { name: 'Create User' }))

    expect(onSave).toHaveBeenCalledOnce()
    const payload = onSave.mock.calls[0][0]
    expect(payload.accessible_modules).toContain(selected)
    expect(payload.accessible_modules).not.toContain(excluded)
  })

  it('preselects split permissions independently when editing', () => {
    const existing: UserResponse = {
      id: 'user-1',
      email: 'roc@example.com',
      full_name: 'ROC User',
      role: 'employee',
      manager_id: null,
      designation: null,
      department: null,
      is_active: true,
      deleted_at: null,
      accessible_modules: ['roc'],
      company_id: 'company-1',
      created_at: '2026-08-03T00:00:00Z',
    }
    render(
      <UserModal
        isOpen
        onClose={vi.fn()}
        onSave={vi.fn()}
        initialData={existing}
      />,
    )

    expect(screen.getByRole('checkbox', { name: 'ROC Compliance' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'SecretarialEase' })).not.toBeChecked()
  })

  it('keeps module switches read-only for admins', () => {
    const admin: UserResponse = {
      id: 'admin-1',
      email: 'admin@example.com',
      full_name: 'Admin User',
      role: 'admin',
      manager_id: null,
      designation: null,
      department: null,
      is_active: true,
      deleted_at: null,
      accessible_modules: [],
      company_id: 'company-1',
      created_at: '2026-08-03T00:00:00Z',
    }
    render(
      <UserModal
        isOpen
        onClose={vi.fn()}
        onSave={vi.fn()}
        initialData={admin}
      />,
    )

    expect(screen.getByText('Admins automatically have access to all modules.')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'ROC Compliance' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'SecretarialEase' })).not.toBeInTheDocument()
  })

  it('allows toggling can_change_password for users', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(
      <UserModal
        isOpen
        onClose={vi.fn()}
        onSave={onSave}
        initialData={null}
      />,
    )

    const pwdSwitch = screen.getByRole('checkbox', { name: 'Allow user to change their password' })
    expect(pwdSwitch).toBeChecked()

    // Toggle off
    await user.click(pwdSwitch)
    expect(pwdSwitch).not.toBeChecked()

    const dialog = screen.getByRole('dialog', { name: 'New User' })
    const inputs = within(dialog).getAllByRole('textbox')
    await user.type(inputs[0], 'No Pwd User')
    await user.type(inputs[1], 'nopwd@example.com')
    const password = dialog.querySelector<HTMLInputElement>('input[type="password"]')
    await user.type(password!, 'Pass1234!')
    await user.click(screen.getByRole('button', { name: 'Create User' }))

    expect(onSave).toHaveBeenCalledOnce()
    const payload = onSave.mock.calls[0][0]
    expect(payload.can_change_password).toBe(false)
  })
})

