import { companyClient } from '@/api/clients/company'
import type {
  AuditEngagementResponse,
  AuditEngagementCreate,
  AuditorInvite,
  EntryApproval,
  TrialBalanceAccountResponse,
  RequirementRequestResponse,
  RequirementFulfill,
  QueryResponse,
  QueryMessageResponse,
  QueryMessageCreate,
} from '@/api/types'

/** AuditEase — company side (`/api/v1/auditease`). Company_user identity only. */
export const auditeaseCompanyApi = {
  importTrialBalance: (formData: FormData) =>
    companyClient.post<TrialBalanceAccountResponse[]>('/api/v1/auditease/trial-balance/import', {
      formData,
    }),
  getTrialBalance: () =>
    companyClient.get<TrialBalanceAccountResponse[]>('/api/v1/auditease/trial-balance'),
  mapLedgerGroup: (ledgerId: string, body: { group: string }) =>
    companyClient.post<TrialBalanceAccountResponse>(
      `/api/v1/auditease/ledgers/${ledgerId}/map-group`,
      { body },
    ),

  listEngagements: () =>
    companyClient.get<AuditEngagementResponse[]>('/api/v1/auditease/engagements'),
  createEngagement: (body: AuditEngagementCreate) =>
    companyClient.post<AuditEngagementResponse>('/api/v1/auditease/engagements', { body }),
  closeEngagement: (id: string) =>
    companyClient.patch<AuditEngagementResponse>(`/api/v1/auditease/engagements/${id}/close`),
  inviteAuditor: (id: string, body: AuditorInvite) =>
    companyClient.post<AuditEngagementResponse>(
      `/api/v1/auditease/engagements/${id}/invite-auditor`,
      { body },
    ),

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
    companyClient.get<QueryResponse[]>(
      `/api/v1/auditease/engagements/${engagementId}/queries`,
    ),
  addQueryMessage: (engagementId: string, queryId: string, body: QueryMessageCreate) =>
    companyClient.post<QueryMessageResponse>(
      `/api/v1/auditease/engagements/${engagementId}/queries/${queryId}/messages`,
      { body },
    ),
}
