import { describe, expect, it } from 'vitest'
import { buildRequirementPayload, validateRequirementForm } from './requirementForm'

describe('validateRequirementForm', () => {
  const base = {
    description: '',
    priority: 1,
    period_from: '',
    period_to: '',
    due_date: '',
  }

  it('rejects empty requirement text', () => {
    expect(validateRequirementForm({ ...base, description: '   ' })).toBe('Requirement text is required')
  })

  it('rejects period_to before period_from', () => {
    expect(
      validateRequirementForm({
        ...base,
        description: 'X',
        period_from: '2026-01-01',
        period_to: '2025-01-01',
      }),
    ).toBe('"Period to" must be on or after "Period from"')
  })

  it('rejects past due dates', () => {
    expect(validateRequirementForm({ ...base, description: 'X', due_date: '2000-01-01' })).toBe(
      'Due date cannot be in the past',
    )
  })

  it('accepts a minimal valid form', () => {
    expect(validateRequirementForm({ ...base, description: 'Bank stmts' })).toBeNull()
  })
})

describe('buildRequirementPayload', () => {
  it('trims, drops empties, keeps defaults', () => {
    expect(buildRequirementPayload({ description: '  Bank stmts ', priority: 1, entity: '  ' })).toEqual({
      description: 'Bank stmts',
      priority: 1,
      expected_format: 'any',
    })
  })

  it('keeps explicit non-defaults', () => {
    expect(
      buildRequirementPayload({
        description: 'X',
        priority: 4,
        due_date: '2030-01-01',
        expected_format: 'file',
      }),
    ).toEqual({ description: 'X', priority: 4, due_date: '2030-01-01', expected_format: 'file' })
  })
})
