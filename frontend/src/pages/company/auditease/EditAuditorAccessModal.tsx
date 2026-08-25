import { useEffect, useState } from 'react'
import { Modal, Button, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import type { EngagementAuditorResponse } from '@/api/types'
import { useUpdateAuditorAccess } from '@/api/hooks/auditease'

type Areas = Record<string, boolean>

const AREAS: { key: string; label: string }[] = [
  { key: 'trial_balance', label: 'Trial Balance' },
  { key: 'entries', label: 'Entries' },
  { key: 'requirements', label: 'Requirements' },
  { key: 'queries', label: 'Queries' },
  { key: 'documents', label: 'Documents' },
]

export function EditAuditorAccessModal({
  open,
  onClose,
  engagementId,
  auditor,
}: {
  open: boolean
  onClose: () => void
  engagementId: string
  auditor: EngagementAuditorResponse | null
}) {
  const toast = useToast()
  const update = useUpdateAuditorAccess(engagementId)
  const [areas, setAreas] = useState<Areas>({})

  useEffect(() => {
    if (auditor) setAreas({ ...auditor.area_permissions })
  }, [auditor])

  if (!auditor) return null

  const submit = async () => {
    if (!auditor.auditor_id) return
    try {
      await update.mutateAsync({ auditorId: auditor.auditor_id, body: { area_permissions: areas } })
      toast.success('Access updated')
      onClose()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Update failed')
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Edit access — ${auditor.name ?? auditor.email}`}
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={update.isPending}>Save</Button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        <p className="text-sm text-text-secondary">
          Choose which parts of AuditEase {auditor.name ?? auditor.email} can work in. Changes take effect immediately.
        </p>
        {AREAS.map(({ key, label }) => (
          <label key={key} className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <span className="text-sm">{label}</span>
            <input
              type="checkbox"
              checked={!!areas[key]}
              onChange={(e) => setAreas((prev) => ({ ...prev, [key]: e.target.checked }))}
              className="h-4 w-4"
            />
          </label>
        ))}
      </div>
    </Modal>
  )
}
