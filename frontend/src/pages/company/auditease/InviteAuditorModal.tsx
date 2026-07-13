import { useState } from 'react'
import { Modal, Button, Field, Input, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useInviteAuditor } from '@/api/hooks/auditease'

export function InviteAuditorModal({
  open,
  onClose,
  engagementId,
  currentEmail,
}: {
  open: boolean
  onClose: () => void
  engagementId: string
  currentEmail?: string | null
}) {
  const toast = useToast()
  const invite = useInviteAuditor()
  const [email, setEmail] = useState('')

  const submit = async () => {
    const value = email.trim()
    if (!value) return
    try {
      await invite.mutateAsync({ id: engagementId, body: { email: value } })
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
        {currentEmail && (
          <p className="text-sm text-text-secondary">
            Currently invited: <span className="font-medium text-text-primary">{currentEmail}</span>.
            Inviting a new auditor replaces this one.
          </p>
        )}
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
      </div>
    </Modal>
  )
}
