import { useState, useEffect } from 'react'
import { Modal, Button, Field, Input, Select, Switch } from '@/components/ui'
import { MODULE_DEFINITIONS, type ModuleId } from '@/auth/company/modules'
import type { UserCreate, UserUpdate, UserResponse } from '@/api/types'
import { passwordRules } from '@/utils/passwordValidation'

interface UserModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (data: UserCreate | UserUpdate) => Promise<void>
  onDelete?: (id: string) => Promise<void>
  onDeactivate?: (id: string) => Promise<void>
  onReactivate?: (id: string) => Promise<void>
  /** Whether the current user may manage (deactivate/delete) the edited user (admin, not self). */
  canManage?: boolean
  initialData?: UserResponse | null
}

export function UserModal({ isOpen, onClose, onSave, onDelete, onDeactivate, onReactivate, canManage, initialData }: UserModalProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<'admin' | 'employee'>('employee')
  const [department, setDepartment] = useState('')
  const [designation, setDesignation] = useState('')
  const [accessibleModules, setAccessibleModules] = useState<ModuleId[]>([])
  const [canChangePassword, setCanChangePassword] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isToggling, setIsToggling] = useState(false)

  // Status of the user being edited (new users have no status yet).
  const isDeleted = !!initialData?.deleted_at
  const isInactive = !!initialData && !initialData.is_active && !isDeleted

  useEffect(() => {
    setError(null)
    setConfirmingDelete(false)
    if (initialData) {
      setEmail(initialData.email)
      setFullName(initialData.full_name)
      setRole(initialData.role === 'admin' ? 'admin' : 'employee')
      setDepartment(initialData.department || '')
      setDesignation(initialData.designation || '')
      setAccessibleModules(initialData.accessible_modules as ModuleId[] || [])
      setCanChangePassword(initialData.can_change_password !== false)
    } else {
      setEmail('')
      setPassword('')
      setFullName('')
      setRole('employee')
      setDepartment('')
      setDesignation('')
      setAccessibleModules([])
      setCanChangePassword(true)
    }
  }, [initialData, isOpen])

  const toggleModule = (modId: ModuleId) => {
    setAccessibleModules((prev) =>
      prev.includes(modId) ? prev.filter((m) => m !== modId) : [...prev, modId]
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError(null)

    if (!initialData) {
      if (password.length < passwordRules.minLength.value) {
        setError(passwordRules.minLength.message)
        setIsSubmitting(false)
        return
      }
      if (password.length > passwordRules.maxLength.value) {
        setError(passwordRules.maxLength.message)
        setIsSubmitting(false)
        return
      }
      if (!passwordRules.pattern.value.test(password)) {
        setError(passwordRules.pattern.message)
        setIsSubmitting(false)
        return
      }
    }

    try {
      if (initialData) {
        const update: UserUpdate = {
          full_name: fullName,
          role,
          department,
          designation,
          accessible_modules: accessibleModules,
          can_change_password: canChangePassword,
        }
        await onSave(update)
      } else {
        const create: UserCreate = {
          email,
          password,
          full_name: fullName,
          role,
          department,
          designation,
          accessible_modules: accessibleModules,
          can_change_password: canChangePassword,
        }
        await onSave(create)
      }
      // Only close on success — otherwise keep the modal open with the error
      // shown, so the admin can correct and retry.
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save user')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!initialData || !onDelete) return
    setIsDeleting(true)
    setError(null)
    try {
      await onDelete(initialData.id)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete user')
      setConfirmingDelete(false)
    } finally {
      setIsDeleting(false)
    }
  }

  const handleToggleActive = async () => {
    if (!initialData) return
    const action = isInactive ? onReactivate : onDeactivate
    if (!action) return
    setIsToggling(true)
    setError(null)
    try {
      await action(initialData.id)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update user')
    } finally {
      setIsToggling(false)
    }
  }

  const isAdmin = role === 'admin'
  const busy = isSubmitting || isDeleting || isToggling

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title={initialData ? 'Edit User' : 'New User'}
    >
      <form onSubmit={handleSubmit} className="space-y-6">
        {error && (
          <div className="rounded-btn border border-status-action/40 bg-status-action/10 px-3 py-2 text-sm font-medium text-status-action">
            {error}
          </div>
        )}
        <div className="grid grid-cols-2 gap-4">
          <Field label="Full Name" required>
            <Input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </Field>
          <Field label="Email" required>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={!!initialData}
            />
          </Field>
          {!initialData && (
            <Field label="Password" required>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
          )}
          <Field label="Role">
            <Select
              value={role}
              onChange={(e) => setRole(e.target.value as typeof role)}
            >
              <option value="admin">Admin</option>
              <option value="employee">Employee</option>
            </Select>
          </Field>
          <Field label="Department">
            <Input
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
            />
          </Field>
          <Field label="Designation">
            <Input
              value={designation}
              onChange={(e) => setDesignation(e.target.value)}
            />
          </Field>
        </div>

        <div>
          <h4 className="text-sm font-medium text-text-primary mb-3 border-b border-border pb-2">
            Module Access
          </h4>
          {isAdmin ? (
            <p className="text-sm text-text-secondary">
              Admins automatically have access to all modules.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {MODULE_DEFINITIONS.map(({ id, label }) => (
                <Switch
                  key={id}
                  checked={accessibleModules.includes(id)}
                  onChange={() => toggleModule(id)}
                  label={label}
                />
              ))}
            </div>
          )}
        </div>

        <div>
          <h4 className="text-sm font-medium text-text-primary mb-3 border-b border-border pb-2">
            Security & Credentials
          </h4>
          <Switch
            checked={canChangePassword}
            onChange={setCanChangePassword}
            label="Allow user to change their password"
          />
        </div>

        <div className="flex items-center justify-between gap-3 pt-4 border-t border-border">
          <div className="flex items-center gap-2">
            {initialData && isDeleted ? (
              <span className="text-sm text-text-muted">This user has been deleted.</span>
            ) : initialData && canManage ? (
              confirmingDelete ? (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-text-secondary">
                    Delete this user? Their login is disabled and email freed; their name stays on files they created.
                  </span>
                  <Button variant="danger" type="button" loading={isDeleting} onClick={handleDelete}>
                    Yes, delete
                  </Button>
                  <Button variant="ghost" type="button" onClick={() => setConfirmingDelete(false)} disabled={isDeleting}>
                    No
                  </Button>
                </div>
              ) : (
                <>
                  {(onDeactivate || onReactivate) && (
                    <Button variant="ghost" type="button" onClick={handleToggleActive} loading={isToggling} disabled={busy}>
                      {isInactive ? 'Reactivate' : 'Deactivate'}
                    </Button>
                  )}
                  {onDelete && (
                    <Button variant="ghost" type="button" onClick={() => setConfirmingDelete(true)} disabled={busy}>
                      <span className="text-status-action">Delete user</span>
                    </Button>
                  )}
                </>
              )
            ) : null}
          </div>
          <div className="flex gap-3">
            <Button variant="ghost" type="button" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            {!isDeleted && (
              <Button type="submit" variant="primary" loading={isSubmitting} disabled={isDeleting || isToggling}>
                {initialData ? 'Save Changes' : 'Create User'}
              </Button>
            )}
          </div>
        </div>
      </form>
    </Modal>
  )
}
