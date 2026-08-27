import { useState } from 'react'
import { Button, Field, Input, Modal, Select, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useAuditorCreateRequirement, useAuditorUpdateRequirement } from '@/api/hooks/auditorEngagements'
import type { RequirementRequestResponse } from '@/api/types'
import {
  buildRequirementPayload,
  validateRequirementForm,
  type RequirementFormState,
} from './requirementForm'

export function NewRequirementModal({
  engagementId,
  nextReqId,
  initial,
  onClose,
}: {
  engagementId: string
  nextReqId?: string
  initial?: RequirementRequestResponse | null
  onClose: () => void
}) {
  const toast = useToast()
  const createReq = useAuditorCreateRequirement()
  const updateReq = useAuditorUpdateRequirement()

  const [form, setForm] = useState<RequirementFormState>({
    description: initial?.description ?? '',
    priority: initial?.priority ?? 1,
    due_date: initial?.due_date ?? '',
  })
  const [error, setError] = useState<string | null>(null)

  const isEditing = !!initial

  const set = <K extends keyof RequirementFormState>(key: K, value: RequirementFormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const handleSubmit = async () => {
    const problem = validateRequirementForm(form)
    if (problem) {
      setError(problem)
      return
    }
    try {
      const payload = buildRequirementPayload(form)
      if (isEditing) {
        await updateReq.mutateAsync({
          engagementId,
          reqId: initial.id,
          body: payload,
        })
        toast.success(`Requirement ${initial.requirement_id_str || initial.id} updated`)
      } else {
        await createReq.mutateAsync({
          engagementId,
          body: payload,
        })
        toast.success(`Requirement ${nextReqId || ''} requested`)
      }
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    }
  }

  const isPending = createReq.isPending || updateReq.isPending

  return (
    <Modal
      open
      onClose={onClose}
      title={isEditing ? `Edit requirement (${initial.requirement_id_str || ''})` : 'New requirement'}
      size="md"
    >
      {!isEditing && nextReqId && (
        <p className="-mt-2 mb-4 text-sm text-text-muted">Will be filed as {nextReqId}</p>
      )}
      <div className="flex flex-col gap-4">
        <Field label="Requirement" required hint="What you are asking the company to provide.">
          <Textarea
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="e.g. FY24 bank statements for all current accounts"
            rows={4}
            autoFocus
          />
        </Field>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Priority" hint="1 = routine · 5 = critical">
            <Select
              value={String(form.priority)}
              onChange={(e) => set('priority', Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  P{n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Due date" hint="Optional">
            <Input
              type="date"
              value={form.due_date}
              onChange={(e) => set('due_date', e.target.value)}
            />
          </Field>
        </div>

        {error && <p className="text-sm font-medium text-status-action">{error}</p>}

        <div className="flex items-center justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={isPending || !form.description.trim()}>
            {isPending ? (isEditing ? 'Saving…' : 'Requesting…') : isEditing ? 'Save changes' : 'Request'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
