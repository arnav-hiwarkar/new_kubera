import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { auditeaseCompanyApi } from '@/api/endpoints/auditease'
import type {
  AuditEngagementCreate,
  AuditorInvite,
  LedgerGroupCreate,
  LedgerGroupRename,
  BulkMapRequest,
  UnmapRequest,
  MappingImportRequest,
  EntryApproval,
} from '@/api/types'

export const auditeaseKeys = {
  engagements: ['auditease', 'engagements'] as const,
  engagement: (id: string) => ['auditease', 'engagement', id] as const,
  trialBalance: (id: string) => ['auditease', 'trial-balance', id] as const,
  ledgerGroups: ['auditease', 'ledger-groups'] as const,
  entries: (id: string) => ['auditease', 'entries', id] as const,
  mappingSources: (id: string) => ['auditease', 'mapping-sources', id] as const,
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

// --- Chart of accounts ---

export function useLedgerGroups() {
  return useQuery({
    queryKey: auditeaseKeys.ledgerGroups,
    queryFn: () => auditeaseCompanyApi.listLedgerGroups(),
  })
}

function useInvalidateGroups() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: auditeaseKeys.ledgerGroups })
}

export function useCreateLedgerGroup() {
  const invalidate = useInvalidateGroups()
  return useMutation({
    mutationFn: (body: LedgerGroupCreate) => auditeaseCompanyApi.createLedgerGroup(body),
    onSuccess: invalidate,
  })
}

export function useRenameLedgerGroup() {
  const invalidate = useInvalidateGroups()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: LedgerGroupRename }) =>
      auditeaseCompanyApi.renameLedgerGroup(id, body),
    onSuccess: invalidate,
  })
}

export function useDeleteLedgerGroup() {
  const invalidate = useInvalidateGroups()
  return useMutation({
    mutationFn: (id: string) => auditeaseCompanyApi.deleteLedgerGroup(id),
    onSuccess: invalidate,
  })
}

// --- Mapping ---

export function useMapLedger() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, ledgerId, groupId }: { engagementId: string; ledgerId: string; groupId: string }) =>
      auditeaseCompanyApi.mapLedger(engagementId, ledgerId, { group_id: groupId }),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: auditeaseKeys.trialBalance(engagementId) }),
  })
}

export function useBulkMapLedgers() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, body }: { engagementId: string; body: BulkMapRequest }) =>
      auditeaseCompanyApi.bulkMapLedgers(engagementId, body),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: auditeaseKeys.trialBalance(engagementId) }),
  })
}

export function useUnmapLedgers() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, body }: { engagementId: string; body: UnmapRequest }) =>
      auditeaseCompanyApi.unmapLedgers(engagementId, body),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: auditeaseKeys.trialBalance(engagementId) }),
  })
}

export function useMappingSources(engagementId: string, enabled = true) {
  return useQuery({
    queryKey: auditeaseKeys.mappingSources(engagementId),
    queryFn: () => auditeaseCompanyApi.listMappingSources(engagementId),
    enabled: enabled && !!engagementId,
  })
}

export function useImportMappings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      engagementId,
      body,
    }: {
      engagementId: string
      body: MappingImportRequest
    }) => auditeaseCompanyApi.importMappings(engagementId, body),
    onSuccess: (_result, { engagementId }) =>
      qc.invalidateQueries({ queryKey: auditeaseKeys.trialBalance(engagementId) }),
  })
}


// --- Requirements ---

export function useListRequirements(engagementId: string) {
  return useQuery({
    queryKey: ['auditease', 'requirements', engagementId],
    queryFn: () => auditeaseCompanyApi.listRequirements(engagementId),
    enabled: !!engagementId,
  })
}

export function useFulfillRequirement() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, reqId, body }: { engagementId: string; reqId: string; body: import('@/api/types').RequirementFulfill }) =>
      auditeaseCompanyApi.fulfillRequirement(engagementId, reqId, body),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditease', 'requirements', engagementId] }),
  })
}

// --- Queries ---

export function useListQueries(engagementId: string) {
  return useQuery({
    queryKey: ['auditease', 'queries', engagementId],
    queryFn: () => auditeaseCompanyApi.listQueries(engagementId),
    enabled: !!engagementId,
    refetchInterval: 5000,
  })
}

export function useAddQueryMessage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ engagementId, queryId, formData }: { engagementId: string; queryId: string; formData: FormData }) =>
      auditeaseCompanyApi.addQueryMessage(engagementId, queryId, formData),
    onSuccess: (_r, { engagementId }) =>
      qc.invalidateQueries({ queryKey: ['auditease', 'queries', engagementId] }),
  })
}
// --- Entries ---

export function useListEntries(engagementId: string) {
  return useQuery({
    queryKey: auditeaseKeys.entries(engagementId),
    queryFn: () => auditeaseCompanyApi.listEntries(engagementId),
    enabled: !!engagementId,
  })
}

export function useApproveRejectEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, body }: { entryId: string; body: EntryApproval }) =>
      auditeaseCompanyApi.approveRejectEntry(entryId, body),
    onSuccess: () => {
      // Invalidate all entries to refresh the list
      qc.invalidateQueries({ queryKey: ['auditease', 'entries'] })
      // We should also invalidate the trial balance if we want it to reflect approved entries,
      // but for V1 we can invalidate both just in case.
      qc.invalidateQueries({ queryKey: ['auditease', 'trial-balance'] })
      // Approving/rejecting an entry changes the report figures.
      qc.invalidateQueries({ queryKey: ['auditease', 'report-preview'] })
    },
  })
}

// --- Reports ---

export function usePreviewReport(engagementId: string) {
  return useQuery({
    queryKey: ['auditease', 'report-preview', engagementId],
    queryFn: () => auditeaseCompanyApi.previewReport(engagementId),
    enabled: !!engagementId,
  })
}

export function useGenerateReport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (engagementId: string) => auditeaseCompanyApi.generateReport(engagementId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['docvault', 'documents'] })
    },
  })
}
