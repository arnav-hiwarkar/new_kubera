import type { RequirementRequestCreate } from '@/api/types'

export interface RequirementFormState {
  description: string
  priority: number
  due_date: string
}

export const initialRequirementFormState: RequirementFormState = {
  description: '',
  priority: 1,
  due_date: '',
}

export function validateRequirementForm(
  f: Pick<RequirementFormState, 'description' | 'due_date'>
): string | null {
  if (!f.description.trim()) return 'Requirement description is required'
  return null
}

export function buildRequirementPayload(
  f: Partial<RequirementFormState>
): RequirementRequestCreate {
  const payload: RequirementRequestCreate = {
    description: (f.description ?? '').trim(),
    priority: f.priority ?? 1,
  }
  const dueDate = (f.due_date ?? '').trim()
  if (dueDate) {
    payload.due_date = dueDate
  }
  return payload
}

