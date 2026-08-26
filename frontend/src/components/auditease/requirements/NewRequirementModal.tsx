import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Button, Field, Input, Modal, Select, Textarea, useToast } from '@/components/ui'
import { ApiError } from '@/api/http'
import { useAuditorCreateRequirement } from '@/api/hooks/auditorEngagements'
import { buildRequirementPayload, validateRequirementForm } from './requirementForm'

type FormState = import('./requirementForm').RequirementFormState

const EMPTY: FormState = {
  description: '',
  title: '',
  priority: 1,
  due_date: '',
  additional_details: '',
  period_from: '',
  period_to: '',
  entity: '',
  responsible_person_id: '',
  expected_format: 'any',
  auditor_notes: '',
  parent_requirement_id: '',
}

export function NewRequirementModal({
  engagementId,
  nextReqId,
  companyUsers,
  onClose,
}: {
  engagementId: string
  nextReqId: string
  companyUsers: { id: string; name: string }[]
  onClose: () => void
}) {
  const toast = useToast()
  const createReq = useAuditorCreateRequirement()
  const [form, setForm] = useState<FormState>(EMPTY)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const handleSubmit = async () => {
    const problem = validateRequirementForm(form)
    if (problem) {
      setError(problem)
      return
    }
    try {
      await createReq.mutateAsync({ engagementId, body: buildRequirementPayload(form) })
      toast.success(`Requirement ${nextReqId} requested`)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    }
  }

  return (
    <Modal open onClose={onClose} title="New requirement" size="lg">
      <p className="-mt-2 mb-4 text-sm text-text-muted">Will be filed as {nextReqId}</p>
      <div className="flex flex-col gap-4">
        <Field label="Requirement" required hint="What you are asking the company to provide.">
          <Textarea
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="e.g. FY24 bank statements for all current accounts"
            rows={3}
            autoFocus
          />
        </Field>

        {/* Visible by default per spec: priority preset to 1, due date optional & unset */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Priority" hint="1 = routine · 5 = critical">
            <Select value={String(form.priority)} onChange={(e) => set('priority', Number(e.target.value))}>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  P{n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Due date" hint="Optional">
            <Input type="date" value={form.due_date} onChange={(e) => set('due_date', e.target.value)} />
          </Field>
        </div>

        {error && <p className="text-sm font-medium text-status-action">{error}</p>}

        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setAdvancedOpen((o) => !o)}
            aria-expanded={advancedOpen}
            className="flex items-center gap-2 rounded-btn px-1 py-1 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary"
          >
            <ChevronDown
              className={`h-4 w-4 transition-transform duration-200 ease-spring ${advancedOpen ? 'rotate-180' : ''}`}
            />
            Advanced options
          </button>
          <Button onClick={() => void handleSubmit()} disabled={createReq.isPending || !form.description.trim()}>
            {createReq.isPending ? 'Requesting…' : 'Request'}
          </Button>
        </div>

        {/* Progressive disclosure: grid-rows trick animates open without measuring height */}
        <div
          className="grid transition-[grid-template-rows] duration-300 ease-nav"
          style={{ gridTemplateRows: advancedOpen ? '1fr' : '0fr' }}
        >
          <div className="overflow-hidden">
            <div className="flex flex-col gap-4 border-t border-border pt-4">
              <Field label="Title" hint="Short label — defaults to the first line of the requirement.">
                <Input value={form.title} onChange={(e) => set('title', e.target.value)} />
              </Field>
              <Field label="Additional details">
                <Textarea rows={2} value={form.additional_details} onChange={(e) => set('additional_details', e.target.value)} />
              </Field>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Period from">
                  <Input type="date" value={form.period_from} onChange={(e) => set('period_from', e.target.value)} />
                </Field>
                <Field label="Period to">
                  <Input type="date" value={form.period_to} onChange={(e) => set('period_to', e.target.value)} />
                </Field>
              </div>
              <Field label="Entity" hint="Group company / branch this applies to.">
                <Input value={form.entity} onChange={(e) => set('entity', e.target.value)} placeholder="e.g. ETHDC Main" />
              </Field>
              {companyUsers.length > 0 && (
                <Field label="Responsible person (company)">
                  <Select
                    value={form.responsible_person_id}
                    onChange={(e) => set('responsible_person_id', e.target.value)}
                  >
                    <option value="">Unassigned</option>
                    {companyUsers.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              <Field label="Expected format" hint="A hint for the company — they can always answer either way.">
                <Select
                  value={form.expected_format}
                  onChange={(e) => set('expected_format', e.target.value as FormState['expected_format'])}
                >
                  <option value="any">Any</option>
                  <option value="text">Typed answer</option>
                  <option value="file">Document</option>
                </Select>
              </Field>
              <Field label="Parent requirement" hint="Files this as a child request under an existing REQ.">
                <Input
                  value={form.parent_requirement_id}
                  onChange={(e) => set('parent_requirement_id', e.target.value)}
                  placeholder="Paste a requirement id…"
                />
              </Field>
              <Field label="Auditor notes" hint="Visible to auditors only.">
                <Textarea rows={2} value={form.auditor_notes} onChange={(e) => set('auditor_notes', e.target.value)} />
              </Field>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}
