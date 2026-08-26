import { describe, expect, it } from 'vitest'
import { computeCounts, percentComplete } from './progress'

const req = (status: string) => ({ status })

describe('computeCounts', () => {
  it('counts each bucket', () => {
    expect(
      computeCounts([
        req('accepted'),
        req('accepted'),
        req('submitted'),
        req('clarification_needed'),
        req('pending'),
      ]),
    ).toEqual({ accepted: 2, submitted: 1, clarification_needed: 1, pending: 1 })
  })

  it('handles empty list', () => {
    expect(computeCounts([]).accepted).toBe(0)
  })

  it('ignores unknown statuses', () => {
    expect(computeCounts([req('weird')])).toEqual({
      accepted: 0,
      submitted: 0,
      clarification_needed: 0,
      pending: 0,
    })
  })
})

describe('percentComplete', () => {
  it('is accepted share rounded', () => {
    expect(percentComplete([req('accepted'), req('pending')])).toBe(50)
    expect(percentComplete([])).toBe(0)
  })
})
