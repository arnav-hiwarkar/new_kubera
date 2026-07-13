import { auditorClient } from '@/api/clients/auditor'
import type {
  AuditEngagementResponse,
  TrialBalanceAccountResponse,
  AuditEntryCreate,
  AuditEntryResponse,
  RequirementRequestCreate,
  RequirementRequestResponse,
  QueryCreate,
  QueryResponse,
  QueryMessageCreate,
  QueryMessageResponse,
} from '@/api/types'

/**
 * AuditEase — auditor side (`/api/v1/auditor`). Auditor identity ONLY.
 * This is the auditor's entire route tree on the backend.
 */
export const auditorEngagementsApi = {
  listEngagements: () =>
    auditorClient.get<AuditEngagementResponse[]>('/api/v1/auditor/engagements'),
  acceptEngagement: (id: string) =>
    auditorClient.post<AuditEngagementResponse>(`/api/v1/auditor/engagements/${id}/accept`),
  getTrialBalance: (id: string) =>
    auditorClient.get<TrialBalanceAccountResponse[]>(
      `/api/v1/auditor/engagements/${id}/trial-balance`,
    ),
  createEntry: (id: string, body: AuditEntryCreate) =>
    auditorClient.post<AuditEntryResponse>(`/api/v1/auditor/engagements/${id}/entries`, {
      body,
    }),
  createRequirement: (id: string, body: RequirementRequestCreate) =>
    auditorClient.post<RequirementRequestResponse>(
      `/api/v1/auditor/engagements/${id}/requirement-requests`,
      { body },
    ),
  createQuery: (id: string, body: QueryCreate) =>
    auditorClient.post<QueryResponse>(`/api/v1/auditor/engagements/${id}/queries`, { body }),
  addQueryMessage: (id: string, queryId: string, body: QueryMessageCreate) =>
    auditorClient.post<QueryMessageResponse>(
      `/api/v1/auditor/engagements/${id}/queries/${queryId}/messages`,
      { body },
    ),
}
