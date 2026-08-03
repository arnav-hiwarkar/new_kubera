import { describe, expect, it } from 'vitest'
import { auditeaseKeys } from './auditease'
import { auditorKeys } from './auditorEngagements'

describe('trial-balance query cache versions', () => {
  it('isolates company and auditor v2 envelopes from legacy array caches', () => {
    expect(auditeaseKeys.trialBalance('eng-1')).toEqual([
      'auditease', 'trial-balance-view', 'v2', 'eng-1',
    ])
    expect(auditorKeys.trialBalance('eng-1')).toEqual([
      'auditor', 'trial-balance-view', 'v2', 'eng-1',
    ])
  })
})
