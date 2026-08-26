export type RequestStatusFilter = 'pending' | 'submitted' | 'clarification_needed' | 'accepted'

export interface RequirementLite {
  status: string
}

export function computeCounts(requirements: RequirementLite[]): Record<RequestStatusFilter, number> {
  const counts = { accepted: 0, submitted: 0, clarification_needed: 0, pending: 0 }
  for (const r of requirements) {
    if (r.status in counts) counts[r.status as RequestStatusFilter] += 1
  }
  return counts
}

export function percentComplete(requirements: RequirementLite[]): number {
  if (!requirements.length) return 0
  const accepted = requirements.filter((r) => r.status === 'accepted').length
  return Math.round((accepted / requirements.length) * 100)
}
