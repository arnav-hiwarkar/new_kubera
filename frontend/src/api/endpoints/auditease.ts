import { companyClient } from '@/api/clients/company'
import type {
  AuditEngagementResponse,
  AuditEngagementCreate,
  AuditorInvite,
  EntryApproval,
  TrialBalanceAccountResponse,
  TBInspectResponse,
  TBImportResult,
  LedgerGroupResponse,
  LedgerGroupCreate,
  LedgerGroupRename,
  MapLedgerRequest,
  BulkMapRequest,
  UnmapRequest,
  RequirementRequestResponse,
  RequirementFulfill,
  QueryResponse,
  QueryMessageResponse,
  QueryMessageCreate,
} from '@/api/types'

/** AuditEase — company side (`/api/v1/auditease`). Company_user identity only. */
export const auditeaseCompanyApi = {
  // Engagements
  listEngagements: () =>
    companyClient.get<AuditEngagementResponse[]>('/api/v1/auditease/engagements'),
  getEngagement: (id: string) =>
    companyClient.get<AuditEngagementResponse>(`/api/v1/auditease/engagements/${id}`),
  createEngagement: (body: AuditEngagementCreate) =>
    companyClient.post<AuditEngagementResponse>('/api/v1/auditease/engagements', { body }),
  closeEngagement: (id: string) =>
    companyClient.patch<AuditEngagementResponse>(`/api/v1/auditease/engagements/${id}/close`),
  deleteEngagement: (id: string) =>
    companyClient.delete<void>(`/api/v1/auditease/engagements/${id}`),
  inviteAuditor: (id: string, body: AuditorInvite) =>
    companyClient.post<AuditEngagementResponse>(
      `/api/v1/auditease/engagements/${id}/invite-auditor`,
      { body },
    ),

  // Trial balance (per engagement, server-side file import)
  inspectTrialBalance: (engagementId: string, formData: FormData) =>
    companyClient.post<TBInspectResponse>(
      `/api/v1/auditease/engagements/${engagementId}/trial-balance/inspect`,
      { formData },
    ),
  importTrialBalance: (engagementId: string, formData: FormData) =>
    companyClient.post<TBImportResult>(
      `/api/v1/auditease/engagements/${engagementId}/trial-balance/import`,
      { formData },
    ),
  getTrialBalance: (engagementId: string) =>
    companyClient.get<TrialBalanceAccountResponse[]>(
      `/api/v1/auditease/engagements/${engagementId}/trial-balance`,
    ),

  // Chart of accounts (company-global groups)
  listLedgerGroups: () =>
    companyClient.get<LedgerGroupResponse[]>('/api/v1/auditease/ledger-groups'),
  createLedgerGroup: (body: LedgerGroupCreate) =>
    companyClient.post<LedgerGroupResponse>('/api/v1/auditease/ledger-groups', { body }),
  renameLedgerGroup: (id: string, body: LedgerGroupRename) =>
    companyClient.patch<LedgerGroupResponse>(`/api/v1/auditease/ledger-groups/${id}`, { body }),
  deleteLedgerGroup: (id: string) =>
    companyClient.delete<void>(`/api/v1/auditease/ledger-groups/${id}`),

  // Mapping (per engagement)
  mapLedger: (engagementId: string, ledgerId: string, body: MapLedgerRequest) =>
    companyClient.post<TrialBalanceAccountResponse>(
      `/api/v1/auditease/engagements/${engagementId}/ledgers/${ledgerId}/map`,
      { body },
    ),
  bulkMapLedgers: (engagementId: string, body: BulkMapRequest) =>
    companyClient.post<{ updated: number }>(
      `/api/v1/auditease/engagements/${engagementId}/ledgers/bulk-map`,
      { body },
    ),
  unmapLedgers: (engagementId: string, body: UnmapRequest) =>
    companyClient.post<{ updated: number }>(
      `/api/v1/auditease/engagements/${engagementId}/ledgers/unmap`,
      { body },
    ),

  // Entries / requirements / queries (later slices)
  approveRejectEntry: (entryId: string, body: EntryApproval) =>
    companyClient.patch<unknown>(`/api/v1/auditease/entries/${entryId}/approve`, { body }),
  listRequirements: (engagementId: string) =>
    companyClient.get<RequirementRequestResponse[]>(
      `/api/v1/auditease/engagements/${engagementId}/requirement-requests`,
    ),
  fulfillRequirement: (engagementId: string, reqId: string, body: RequirementFulfill) =>
    companyClient.patch<RequirementRequestResponse>(
      `/api/v1/auditease/engagements/${engagementId}/requirement-requests/${reqId}/fulfill`,
      { body },
    ),
  listQueries: (engagementId: string) =>
    companyClient.get<QueryResponse[]>(`/api/v1/auditease/engagements/${engagementId}/queries`),
  addQueryMessage: (engagementId: string, queryId: string, formData: FormData) =>
    companyClient.post<QueryMessageResponse>(
      `/api/v1/auditease/engagements/${engagementId}/queries/${queryId}/messages`,
      { formData },
    ),
}
