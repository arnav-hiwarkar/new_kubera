type FormStateShape = {
  description: string
  title: string
  priority: number
  due_date: string
  additional_details: string
  period_from: string
  period_to: string
  entity: string
  responsible_person_id: string
  expected_format: 'text' | 'file' | 'any'
  auditor_notes: string
  parent_requirement_id: string
}

export type RequirementFormState = FormStateShape

export function validateRequirementForm(
  f: Pick<FormStateShape, 'description' | 'period_from' | 'period_to' | 'due_date'>,
): string | null {
  if (!f.description.trim()) return 'Requirement text is required'
  if (f.period_from && f.period_to && f.period_to < f.period_from)
    return '"Period to" must be on or after "Period from"'
  if (f.due_date) {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    if (new Date(`${f.due_date}T00:00:00`) < today) return 'Due date cannot be in the past'
  }
  return null
}

function clean(v: string | undefined): string | undefined {
  const t = (v ?? '').trim()
  return t ? t : undefined
}

export function buildRequirementPayload(
  f: Partial<FormStateShape>,
): import('@/api/types').RequirementRequestCreate {
  const payload: Record<string, unknown> = {
    description: (f.description ?? '').trim(),
    priority: f.priority ?? 1,
  }
  const optional = [
    ['title', clean(f.title)],
    ['due_date', clean(f.due_date)],
    ['additional_details', clean(f.additional_details)],
    ['period_from', clean(f.period_from)],
    ['period_to', clean(f.period_to)],
    ['entity', clean(f.entity)],
    ['responsible_person_id', clean(f.responsible_person_id)],
    ['auditor_notes', clean(f.auditor_notes)],
    ['parent_requirement_id', clean(f.parent_requirement_id)],
  ] as const
  for (const [key, value] of optional) if (value !== undefined) payload[key] = value
  payload.expected_format = f.expected_format ?? 'any'
  return payload as import('@/api/types').RequirementRequestCreate
}
