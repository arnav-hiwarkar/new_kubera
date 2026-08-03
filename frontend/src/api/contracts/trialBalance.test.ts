import { describe, expect, it } from 'vitest'
import { ApiContractError, parseTrialBalanceView } from './trialBalance'

const valid = {
  accounts: [],
  totals: {
    groups: [],
    balanced: true,
    statement_ready: false,
    difference: 0,
  },
  sign_convention: null,
  sign_unresolved_count: 0,
  inconsistent_row_count: 0,
  warnings: [],
}

describe('parseTrialBalanceView', () => {
  it('accepts an empty v2 envelope and preserves additional server fields', () => {
    const payload = { ...valid, future_field: 'allowed' }
    expect(parseTrialBalanceView(payload)).toBe(payload)
  })

  it.each([
    ['legacy array', [], 'legacy account array'],
    ['missing accounts', { ...valid, accounts: undefined }, 'accounts'],
    ['invalid accounts', { ...valid, accounts: {} }, 'accounts'],
    ['missing totals', { ...valid, totals: undefined }, 'totals'],
    ['invalid groups', { ...valid, totals: { ...valid.totals, groups: {} } }, 'groups'],
    ['invalid balanced', { ...valid, totals: { ...valid.totals, balanced: 1 } }, 'balanced'],
    ['invalid readiness', { ...valid, totals: { ...valid.totals, statement_ready: 'yes' } }, 'statement_ready'],
    ['invalid warnings', { ...valid, warnings: [1] }, 'warnings'],
  ])('rejects %s', (_label, payload, detail) => {
    expect(() => parseTrialBalanceView(payload)).toThrow(ApiContractError)
    expect(() => parseTrialBalanceView(payload)).toThrow(String(detail))
  })
})
