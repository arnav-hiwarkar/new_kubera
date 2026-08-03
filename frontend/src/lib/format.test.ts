import { describe, expect, it } from 'vitest'
import { formatAccounting, formatAmount, formatDrCr, formatMoney, formatSigned } from './format'

describe('amount formatting', () => {
  it('keeps general money signed instead of silently adding accounting brackets', () => {
    expect(formatMoney(-1234)).toBe('-1,234.00')
    expect(formatSigned(-1234)).toBe('-1,234.00')
  })

  it('offers accounting parentheses only when explicitly selected', () => {
    expect(formatAccounting(-1234)).toBe('(1,234.00)')
    expect(formatAmount(-1234, { style: 'accounting' })).toBe('(1,234.00)')
  })

  it('renders canonical net debit as an explicit Dr/Cr amount', () => {
    expect(formatDrCr(-600)).toEqual({ amount: '600.00', side: 'Cr' })
    expect(formatAmount(-600, { style: 'drcr' })).toBe('600.00 Cr')
  })
})
