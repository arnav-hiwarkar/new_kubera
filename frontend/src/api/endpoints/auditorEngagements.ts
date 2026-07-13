import { auditorClient } from '@/api/clients/auditor'
import type {
  AuditEngagementResponse,
  TrialBalanceAccountResponse,
  AuditEntryCreate,
  AuditEntryResponse,
  RequirementRequestCreate,
  RequirementRequestResponse,
  QueryResponse,
  QueryMessageResponse,
  DocumentResponse,
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
  listEntries: (id: string) =>
    auditorClient.get<AuditEntryResponse[]>(`/api/v1/auditor/engagements/${id}/entries`),
  deleteEntry: (entryId: string) =>
    auditorClient.delete<void>(`/api/v1/auditor/entries/${entryId}`),
  listRequirements: (id: string) =>
    auditorClient.get<RequirementRequestResponse[]>(
      `/api/v1/auditor/engagements/${id}/requirement-requests`,
    ),
  createRequirement: (id: string, body: RequirementRequestCreate) =>
    auditorClient.post<RequirementRequestResponse>(
      `/api/v1/auditor/engagements/${id}/requirement-requests`,
      { body },
    ),
  listQueries: (id: string) =>
    auditorClient.get<QueryResponse[]>(`/api/v1/auditor/engagements/${id}/queries`),
  createQuery: (id: string, formData: FormData) =>
    auditorClient.post<QueryResponse>(`/api/v1/auditor/engagements/${id}/queries`, { formData }),
  addQueryMessage: (id: string, queryId: string, formData: FormData) =>
    auditorClient.post<QueryMessageResponse>(
      `/api/v1/auditor/engagements/${id}/queries/${queryId}/messages`,
      { formData },
    ),
  closeQuery: (id: string, queryId: string) =>
    auditorClient.post<QueryResponse>(`/api/v1/auditor/engagements/${id}/queries/${queryId}/close`),
  getDocument: (id: string) =>
    auditorClient.get<DocumentResponse>(`/api/v1/auditor/documents/${id}`),
  downloadDocument: (id: string) =>
    auditorClient.get<Blob>(`/api/v1/auditor/documents/${id}/download`, { responseType: 'blob' }),
}
