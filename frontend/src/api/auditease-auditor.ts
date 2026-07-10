import { api } from '@/lib/api';
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
  QueryMessageResponse
} from '@/types/auditease';

export const auditeaseAuditorApi = {
  // Engagements
  getEngagements: async () => {
    const { data } = await api.get<AuditEngagementResponse[]>('/auditor/engagements');
    return data;
  },
  acceptEngagement: async (engagementId: string) => {
    await api.post(`/auditor/engagements/${engagementId}/accept`);
  },

  // Trial Balance
  getTrialBalance: async (engagementId: string) => {
    const { data } = await api.get<TrialBalanceAccountResponse[]>(`/auditor/engagements/${engagementId}/trial-balance`);
    return data;
  },

  // Entries
  createEntry: async (engagementId: string, payload: AuditEntryCreate) => {
    const { data } = await api.post<AuditEntryResponse>(`/auditor/engagements/${engagementId}/entries`, payload);
    return data;
  },

  // Requirements
  createRequirement: async (engagementId: string, payload: RequirementRequestCreate) => {
    const { data } = await api.post<RequirementRequestResponse>(`/auditor/engagements/${engagementId}/requirement-requests`, payload);
    return data;
  },

  // Queries
  createQuery: async (engagementId: string, payload: QueryCreate) => {
    const { data } = await api.post<QueryResponse>(`/auditor/engagements/${engagementId}/queries`, payload);
    return data;
  },
  addQueryMessage: async (engagementId: string, queryId: string, payload: QueryMessageCreate) => {
    const { data } = await api.post<QueryMessageResponse>(`/auditor/engagements/${engagementId}/queries/${queryId}/messages`, payload);
    return data;
  }
};
