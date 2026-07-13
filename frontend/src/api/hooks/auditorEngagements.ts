import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { auditorEngagementsApi } from '@/api/endpoints/auditorEngagements'

export const auditorKeys = {
  engagements: ['auditor', 'engagements'] as const,
  trialBalance: (id: string) => ['auditor', 'trial-balance', id] as const,
}

export function useAuditorEngagements() {
  return useQuery({
    queryKey: auditorKeys.engagements,
    queryFn: () => auditorEngagementsApi.listEngagements(),
  })
}

export function useAcceptEngagement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => auditorEngagementsApi.acceptEngagement(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: auditorKeys.engagements }),
  })
}

export function useAuditorTrialBalance(engagementId: string) {
  return useQuery({
    queryKey: auditorKeys.trialBalance(engagementId),
    queryFn: () => auditorEngagementsApi.getTrialBalance(engagementId),
    enabled: !!engagementId,
  })
}
