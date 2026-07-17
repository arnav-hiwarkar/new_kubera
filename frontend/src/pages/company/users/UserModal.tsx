import { useState, useEffect } from 'react'
import { Modal, Button, Field, Input, Select, Switch } from '@/components/ui'
import { MODULE_IDS, type ModuleId } from '@/auth/company/ModuleGuard'
import type { UserCreate, UserUpdate, UserResponse } from '@/api/types'

interface UserModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (data: any) => Promise<void>
  initialData?: UserResponse | null
}

const moduleNames: Record<ModuleId, string> = {
  dashboard: 'Dashboard',
  docvault: 'DocVault',
  sales: 'Sales',
  assets: 'Assets',
  kra: 'KRA & Appraisals',
  auditease: 'AuditEase',
  compliance: 'Compliance',
  notifications: 'Notifications',
  activity: 'Activity Log',
}

export function UserModal({ isOpen, onClose, onSave, initialData }: UserModalProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<'admin' | 'manager' | 'employee'>('employee')
  const [department, setDepartment] = useState('')
  const [designation, setDesignation] = useState('')
  const [accessibleModules, setAccessibleModules] = useState<ModuleId[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    if (initialData) {
      setEmail(initialData.email)
      setFullName(initialData.full_name)
      setRole(initialData.role as any)
      setDepartment(initialData.department || '')
      setDesignation(initialData.designation || '')
      setAccessibleModules(initialData.accessible_modules as ModuleId[] || [])
    } else {
      setEmail('')
      setPassword('')
      setFullName('')
      setRole('employee')
      setDepartment('')
      setDesignation('')
      setAccessibleModules([])
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
    try {
      if (initialData) {
        const update: UserUpdate = {
          full_name: fullName,
          role,
          department,
          designation,
          accessible_modules: accessibleModules,
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

  const isAdmin = role === 'admin'

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
              onChange={(e) => setRole(e.target.value as any)}
            >
              <option value="admin">Admin</option>
              <option value="manager">Manager</option>
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
              {MODULE_IDS.map((modId) => (
                <Switch
                  key={modId}
                  checked={accessibleModules.includes(modId)}
                  onChange={() => toggleModule(modId)}
                  label={moduleNames[modId]}
                />
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-border">
          <Button variant="ghost" type="button" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={isSubmitting}>
            {initialData ? 'Save Changes' : 'Create User'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
