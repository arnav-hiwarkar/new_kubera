import { describe, expect, it } from 'vitest'
import { buildRequirementPayload, validateRequirementForm } from './requirementForm'

describe('validateRequirementForm', () => {
  it('rejects empty requirement description', () => {
    expect(validateRequirementForm({ description: '   ', due_date: '' })).toBe(
      'Requirement description is required'
    )
  })

  it('accepts a minimal valid form', () => {
    expect(validateRequirementForm({ description: 'Bank stmts', due_date: '' })).toBeNull()
  })
})

describe('buildRequirementPayload', () => {
  it('trims description and keeps default priority 1', () => {
    expect(
      buildRequirementPayload({ description: '  Bank stmts ', priority: 1 })
    ).toEqual({
      description: 'Bank stmts',
      priority: 1,
    })
  })

  it('keeps explicit non-defaults and due date', () => {
    expect(
      buildRequirementPayload({
        description: 'Ledgers',
        priority: 4,
        due_date: '2026-12-31',
      })
    ).toEqual({
      description: 'Ledgers',
      priority: 4,
      due_date: '2026-12-31',
    })
  })
})
