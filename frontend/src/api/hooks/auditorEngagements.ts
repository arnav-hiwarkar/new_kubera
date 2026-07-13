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

// --- Entries ---

export function useAuditorListEntries(engagementId: string) {
  return useQuery({
    queryKey: ['auditor', 'entries', engagementId],
    queryFn: () => auditorEngagementsApi.listEntries(engagementId),
    enabled: !!engagementId,
  })
}

export function useAuditorCreateEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, body }: { engagementId: string; body: import('@/api/types').AuditEntryCreate }) =>
      auditorEngagementsApi.createEntry(engagementId, body),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditor', 'entries', engagementId] }),
  })
}

export function useAuditorDeleteEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (entryId: string) => auditorEngagementsApi.deleteEntry(entryId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auditor', 'entries'] }), // invalidate all or specific based on key prefix
  })
}

// --- Requirements ---

export function useAuditorListRequirements(engagementId: string) {
  return useQuery({
    queryKey: ['auditor', 'requirements', engagementId],
    queryFn: () => auditorEngagementsApi.listRequirements(engagementId),
    enabled: !!engagementId,
  })
}

export function useAuditorCreateRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, body }: { engagementId: string; body: import('@/api/types').RequirementRequestCreate }) =>
      auditorEngagementsApi.createRequirement(engagementId, body),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditor', 'requirements', engagementId] }),
  })
}

// --- Queries ---

export function useAuditorListQueries(engagementId: string) {
  return useQuery({
    queryKey: ['auditor', 'queries', engagementId],
    queryFn: () => auditorEngagementsApi.listQueries(engagementId),
    enabled: !!engagementId,
    refetchInterval: 5000,
  })
}

export function useAuditorCreateQuery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, formData }: { engagementId: string; formData: FormData }) =>
      auditorEngagementsApi.createQuery(engagementId, formData),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditor', 'queries', engagementId] }),
  })
}

export function useAuditorAddQueryMessage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, queryId, formData }: { engagementId: string; queryId: string; formData: FormData }) =>
      auditorEngagementsApi.addQueryMessage(engagementId, queryId, formData),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditor', 'queries', engagementId] }),
  })
}

export function useAuditorCloseQuery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, queryId }: { engagementId: string; queryId: string }) =>
      auditorEngagementsApi.closeQuery(engagementId, queryId),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditor', 'queries', engagementId] }),
  })
}

// --- Documents ---

export function useAuditorGetDocument(documentId: string) {
  return useQuery({
    queryKey: ['auditor', 'document', documentId],
    queryFn: () => auditorEngagementsApi.getDocument(documentId),
    enabled: !!documentId,
  })
}

export function useAuditorDownloadDocument() {
  return useMutation({
    mutationFn: (documentId: string) => auditorEngagementsApi.downloadDocument(documentId),
  })
}
