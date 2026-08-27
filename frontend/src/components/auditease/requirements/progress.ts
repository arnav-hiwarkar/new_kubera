import type { RequirementRequestResponse } from '@/api/types'

export type RequirementDisplayState = 'awaiting' | 'responded' | 'closed'

export type RequirementStatusFilter = 'all' | 'open' | 'closed' | 'awaiting' | 'responded'

export interface RequirementsStats {
  total: number
  open: number
  closed: number
  awaiting: number
  responded: number
  closedPercent: number
}

export function deriveDisplayState(
  req: Pick<RequirementRequestResponse, 'status' | 'submission_count'>
): RequirementDisplayState {
  if (req.status === 'closed') return 'closed'
  if ((req.submission_count ?? 0) > 0) return 'responded'
  return 'awaiting'
}

export function computeRequirementsStats(
  items: Pick<RequirementRequestResponse, 'status' | 'submission_count'>[]
): RequirementsStats {
  const total = items.length
  let closed = 0
  let awaiting = 0
  let responded = 0

  for (const item of items) {
    const state = deriveDisplayState(item)
    if (state === 'closed') closed += 1
    else if (state === 'responded') responded += 1
    else awaiting += 1
  }

  const open = total - closed
  const closedPercent = total === 0 ? 0 : Math.round((closed / total) * 100)

  return {
    total,
    open,
    closed,
    awaiting,
    responded,
    closedPercent,
  }
}

export function formatFileSize(bytes?: number | null): string {
  if (bytes === null || bytes === undefined) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

