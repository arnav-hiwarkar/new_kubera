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
  getEntries: async (engagementId: string) => {
    const { data } = await api.get<AuditEntryResponse[]>(`/auditor/engagements/${engagementId}/entries`);
    return data;
  },
  createEntry: async (engagementId: string, payload: AuditEntryCreate) => {
    const { data } = await api.post<AuditEntryResponse>(`/auditor/engagements/${engagementId}/entries`, payload);
    return data;
  },
  updateEntry: async (engagementId: string, entryId: string, payload: AuditEntryCreate) => {
    const { data } = await api.put<AuditEntryResponse>(`/auditor/engagements/${engagementId}/entries/${entryId}`, payload);
    return data;
  },

  // Requirements
  getRequirements: async (engagementId: string) => {
    const { data } = await api.get<RequirementRequestResponse[]>(`/auditor/engagements/${engagementId}/requirements`);
    return data;
  },
  createRequirement: async (engagementId: string, payload: RequirementRequestCreate) => {
    const { data } = await api.post<RequirementRequestResponse>(`/auditor/engagements/${engagementId}/requirements`, payload);
    return data;
  },
  updateRequirement: async (engagementId: string, reqId: string, payload: RequirementRequestCreate) => {
    const { data } = await api.put<RequirementRequestResponse>(`/auditor/engagements/${engagementId}/requirements/${reqId}`, payload);
    return data;
  },
  deleteRequirement: async (engagementId: string, reqId: string) => {
    await api.delete(`/auditor/engagements/${engagementId}/requirements/${reqId}`);
  },

  // Queries
  getQueries: async (engagementId: string) => {
    const { data } = await api.get<QueryResponse[]>(`/auditor/engagements/${engagementId}/queries`);
    return data;
  },
  getQuery: async (engagementId: string, queryId: string) => {
    const { data } = await api.get<QueryResponse>(`/auditor/engagements/${engagementId}/queries/${queryId}`);
    return data;
  },
  createQuery: async (engagementId: string, payload: QueryCreate) => {
    const { data } = await api.post<QueryResponse>(`/auditor/engagements/${engagementId}/queries`, payload);
    return data;
  },
  addQueryMessage: async (engagementId: string, queryId: string, payload: QueryMessageCreate) => {
    const { data } = await api.post<QueryMessageResponse>(`/auditor/engagements/${engagementId}/queries/${queryId}/messages`, payload);
    return data;
  },
  closeQuery: async (engagementId: string, queryId: string) => {
    const { data } = await api.post<QueryResponse>(`/auditor/engagements/${engagementId}/queries/${queryId}/close`);
    return data;
  }
};
