import { describe, expect, it } from 'vitest'
import {
  deriveDisplayState,
  computeRequirementsStats,
  formatFileSize,
} from './progress'

describe('deriveDisplayState', () => {
  it('returns closed when status is closed regardless of submission_count', () => {
    expect(deriveDisplayState({ status: 'closed', submission_count: 0 })).toBe('closed')
    expect(deriveDisplayState({ status: 'closed', submission_count: 3 })).toBe('closed')
  })

  it('returns awaiting when status is open and submission_count is 0', () => {
    expect(deriveDisplayState({ status: 'open', submission_count: 0 })).toBe('awaiting')
  })

  it('returns responded when status is open and submission_count > 0', () => {
    expect(deriveDisplayState({ status: 'open', submission_count: 1 })).toBe('responded')
    expect(deriveDisplayState({ status: 'open', submission_count: 3 })).toBe('responded')
  })
})

describe('computeRequirementsStats', () => {
  it('handles empty list', () => {
    expect(computeRequirementsStats([])).toEqual({
      total: 0,
      open: 0,
      closed: 0,
      awaiting: 0,
      responded: 0,
      closedPercent: 0,
    })
  })

  it('computes stats correctly for mixed list', () => {
    const items = [
      { status: 'closed' as const, submission_count: 2 },
      { status: 'closed' as const, submission_count: 0 },
      { status: 'open' as const, submission_count: 0 },
      { status: 'open' as const, submission_count: 1 },
      { status: 'open' as const, submission_count: 3 },
    ]
    const stats = computeRequirementsStats(items)
    expect(stats.total).toBe(5)
    expect(stats.closed).toBe(2)
    expect(stats.open).toBe(3)
    expect(stats.awaiting).toBe(1)
    expect(stats.responded).toBe(2)
    expect(stats.closedPercent).toBe(40)
  })
})

describe('formatFileSize', () => {
  it('formats bytes, KB, MB and nulls', () => {
    expect(formatFileSize(null)).toBe('')
    expect(formatFileSize(undefined)).toBe('')
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(1024 * 5)).toBe('5.0 KB')
    expect(formatFileSize(1024 * 1024 * 2.5)).toBe('2.5 MB')
  })
})
