import { describe, expect, it } from 'vitest'
import { formatAccounting, formatAmount, formatDrCr, formatIndian, formatMoney, formatSigned } from './format'

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

  it('formats numbers with Indian digit grouping and optional rupee prefix', () => {
    expect(formatIndian(1234567.5)).toBe('12,34,567.50')
    expect(formatIndian(100000)).toBe('1,00,000.00')
    expect(formatIndian(-1234567.5)).toBe('-12,34,567.50')
    expect(formatIndian(1234567.5, { symbol: true })).toBe('₹ 12,34,567.50')
    expect(formatIndian(-1234567.5, { symbol: true })).toBe('-₹ 12,34,567.50')
    expect(formatIndian(null)).toBe('—')
  })
})
