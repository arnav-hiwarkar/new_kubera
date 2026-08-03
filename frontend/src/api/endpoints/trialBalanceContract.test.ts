import { beforeEach, describe, expect, it, vi } from 'vitest'
import { companyClient } from '@/api/clients/company'
import { auditorClient } from '@/api/clients/auditor'
import { ApiContractError } from '@/api/contracts/trialBalance'
import { auditeaseCompanyApi } from './auditease'
import { auditorEngagementsApi } from './auditorEngagements'

vi.mock('@/api/clients/company', () => ({
  companyClient: { get: vi.fn() },
}))

vi.mock('@/api/clients/auditor', () => ({
  auditorClient: { get: vi.fn() },
}))

const envelope = {
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

beforeEach(() => vi.clearAllMocks())

describe('trial-balance endpoint contracts', () => {
  it('validates the company response before returning it', async () => {
    vi.mocked(companyClient.get).mockResolvedValue(envelope)
    await expect(auditeaseCompanyApi.getTrialBalance('eng-1')).resolves.toBe(envelope)
  })

  it('validates the auditor response before returning it', async () => {
    vi.mocked(auditorClient.get).mockResolvedValue(envelope)
    await expect(auditorEngagementsApi.getTrialBalance('eng-1')).resolves.toBe(envelope)
  })

  it('turns the legacy array into a recoverable contract error', async () => {
    vi.mocked(companyClient.get).mockResolvedValue([])
    await expect(auditeaseCompanyApi.getTrialBalance('eng-1')).rejects.toBeInstanceOf(ApiContractError)
  })
})
