import { useState } from 'react'
import { Modal, Button, Field, Input, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useInviteAuditor } from '@/api/hooks/auditease'

const AREAS: { key: string; label: string }[] = [
  { key: 'trial_balance', label: 'Trial Balance' },
  { key: 'entries', label: 'Entries' },
  { key: 'requirements', label: 'Requirements' },
  { key: 'queries', label: 'Queries' },
  { key: 'documents', label: 'Documents' },
]

export function InviteAuditorModal({
  open,
  onClose,
  engagementId,
}: {
  open: boolean
  onClose: () => void
  engagementId: string
}) {
  const toast = useToast()
  const invite = useInviteAuditor()
  const [email, setEmail] = useState('')
  const [areas, setAreas] = useState<Record<string, boolean>>(
    Object.fromEntries(AREAS.map((a) => [a.key, true])),
  )
  const [touched, setTouched] = useState(false)

  const submit = async () => {
    const value = email.trim()
    if (!value) return
    try {
      const body = touched ? { email: value, area_permissions: areas } : { email: value }
      await invite.mutateAsync({ id: engagementId, body })
      toast.success(`Invited ${value}`)
      setEmail('')
      onClose()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Invite failed')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Invite auditor"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} loading={invite.isPending} disabled={!email.trim()}>
            Send invite
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field
          label="Auditor email"
          required
          hint="If they don't have an account yet, the invite is held until they register."
        >
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="auditor@firm.com"
            onKeyDown={(e) => e.key === 'Enter' && submit()}
          />
        </Field>
        <div className="flex flex-col gap-2">
          <p className="text-sm text-text-secondary">Workspace access</p>
          {AREAS.map(({ key, label }) => (
            <label
              key={key}
              className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
            >
              <span className="text-sm">{label}</span>
              <input
                type="checkbox"
                checked={areas[key]}
                onChange={(e) => {
                  setTouched(true)
                  setAreas((prev) => ({ ...prev, [key]: e.target.checked }))
                }}
                className="h-4 w-4"
              />
            </label>
          ))}
        </div>
      </div>
    </Modal>
  )
}
