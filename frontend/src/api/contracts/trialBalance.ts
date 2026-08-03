import type { TrialBalanceViewResponse } from '@/api/types'

const UPDATE_MESSAGE =
  'AuditEase was updated while this page was open. Reload the application to continue.'

export class ApiContractError extends Error {
  readonly contract: string

  constructor(contract: string, detail?: string) {
    super(detail ? `${UPDATE_MESSAGE} (${detail})` : UPDATE_MESSAGE)
    this.name = 'ApiContractError'
    this.contract = contract
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Runtime boundary for the coordinated v2 trial-balance envelope. */
export function parseTrialBalanceView(payload: unknown): TrialBalanceViewResponse {
  const fail = (detail: string): never => {
    throw new ApiContractError('TrialBalanceViewResponse/v2', detail)
  }

  if (!isRecord(payload)) {
    return fail(Array.isArray(payload) ? 'received the legacy account array' : 'response is not an object')
  }
  if (!Array.isArray(payload.accounts)) return fail('accounts is not an array')
  if (!isRecord(payload.totals)) return fail('totals is not an object')
  if (!Array.isArray(payload.totals.groups)) return fail('totals.groups is not an array')
  if (typeof payload.totals.balanced !== 'boolean') return fail('totals.balanced is not a boolean')
  if (typeof payload.totals.statement_ready !== 'boolean') {
    return fail('totals.statement_ready is not a boolean')
  }
  if (typeof payload.totals.difference !== 'number') return fail('totals.difference is not a number')
  if (!Array.isArray(payload.warnings) || payload.warnings.some((warning) => typeof warning !== 'string')) {
    return fail('warnings is not an array of strings')
  }
  if (typeof payload.sign_unresolved_count !== 'number') {
    return fail('sign_unresolved_count is not a number')
  }
  if (typeof payload.inconsistent_row_count !== 'number') {
    return fail('inconsistent_row_count is not a number')
  }

  return payload as TrialBalanceViewResponse
}
