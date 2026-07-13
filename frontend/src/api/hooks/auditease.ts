import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import type { AuditEngagementCreate, AuditorInvite } from '@/api/types'

export const auditeaseKeys = {
  engagements: ['auditease', 'engagements'] as const,
  engagement: (id: string) => ['auditease', 'engagement', id] as const,
  trialBalance: (id: string) => ['auditease', 'trial-balance', id] as const,
}

// --- Engagements ---

export function useEngagements() {
  return useQuery({
    queryKey: auditeaseKeys.engagements,
    queryFn: () => auditeaseCompanyApi.listEngagements(),
  })
}

export function useEngagement(id: string) {
  return useQuery({
    queryKey: auditeaseKeys.engagement(id),
    queryFn: () => auditeaseCompanyApi.getEngagement(id),
    enabled: !!id,
  })
}

function useInvalidateEngagements() {
  const qc = useQueryClient()
  return (id?: string) => {
    qc.invalidateQueries({ queryKey: auditeaseKeys.engagements })
    if (id) qc.invalidateQueries({ queryKey: auditeaseKeys.engagement(id) })
  }
}

export function useCreateEngagement() {
  const invalidate = useInvalidateEngagements()
  return useMutation({
    mutationFn: (body: AuditEngagementCreate) => auditeaseCompanyApi.createEngagement(body),
    onSuccess: () => invalidate(),
  })
}

export function useCloseEngagement() {
  const invalidate = useInvalidateEngagements()
  return useMutation({
    mutationFn: (id: string) => auditeaseCompanyApi.closeEngagement(id),
    onSuccess: (_r, id) => invalidate(id),
  })
}

export function useDeleteEngagement() {
  const invalidate = useInvalidateEngagements()
  return useMutation({
    mutationFn: (id: string) => auditeaseCompanyApi.deleteEngagement(id),
    onSuccess: () => invalidate(),
  })
}

export function useInviteAuditor() {
  const invalidate = useInvalidateEngagements()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AuditorInvite }) =>
      auditeaseCompanyApi.inviteAuditor(id, body),
    onSuccess: (_r, { id }) => invalidate(id),
  })
}

// --- Trial balance ---

export function useCompanyTrialBalance(engagementId: string) {
  return useQuery({
    queryKey: auditeaseKeys.trialBalance(engagementId),
    queryFn: () => auditeaseCompanyApi.getTrialBalance(engagementId),
    enabled: !!engagementId,
  })
}

export function useInspectTrialBalance() {
  return useMutation({
    mutationFn: ({ engagementId, formData }: { engagementId: string; formData: FormData }) =>
      auditeaseCompanyApi.inspectTrialBalance(engagementId, formData),
  })
}

export function useImportTrialBalance() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, formData }: { engagementId: string; formData: FormData }) =>
      auditeaseCompanyApi.importTrialBalance(engagementId, formData),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: auditeaseKeys.trialBalance(engagementId) }),
  })
}
