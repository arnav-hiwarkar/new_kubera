import { api } from '@/lib/api';
import type {
  TrialBalanceAccountResponse,
  TBImportRow,
  AuditEngagementCreate,
  AuditEngagementResponse,
  AuditorInvite,
  RequirementFulfill,
  RequirementRequestResponse,
  QueryMessageCreate,
  QueryMessageResponse,
  QueryResponse,
  EntryApproval,
  AuditEntryResponse
} from '@/types/auditease';

export const auditeaseCompanyApi = {
  // Trial Balance
  importTrialBalance: async (rows: TBImportRow[]) => {
    const { data } = await api.post<TrialBalanceAccountResponse[]>('/auditease/trial-balance/import', rows);
    return data;
  },
  getTrialBalance: async () => {
    const { data } = await api.get<TrialBalanceAccountResponse[]>('/auditease/trial-balance');
    return data;
  },
  mapLedgerGroup: async (ledgerId: string, groupId: string) => {
    const { data } = await api.post<TrialBalanceAccountResponse>(`/auditease/ledgers/${ledgerId}/map-group`, { group_id: groupId });
    return data;
  },

  // Engagements
  getEngagements: async () => {
    const { data } = await api.get<AuditEngagementResponse[]>('/auditease/engagements');
    return data;
  },
  createEngagement: async (payload: AuditEngagementCreate) => {
    const { data } = await api.post<AuditEngagementResponse>('/auditease/engagements', payload);
    return data;
  },
  closeEngagement: async (engagementId: string) => {
    const { data } = await api.patch<AuditEngagementResponse>(`/auditease/engagements/${engagementId}/close`);
    return data;
  },
  inviteAuditor: async (engagementId: string, payload: AuditorInvite) => {
    await api.post(`/auditease/engagements/${engagementId}/invite-auditor`, payload);
  },

  // Entries
  approveEntry: async (entryId: string, payload: EntryApproval) => {
    const { data } = await api.patch<AuditEntryResponse>(`/auditease/entries/${entryId}/approve`, payload);
    return data;
  },

  // Requirements
  getRequirements: async (engagementId: string) => {
    const { data } = await api.get<RequirementRequestResponse[]>(`/auditease/engagements/${engagementId}/requirement-requests`);
    return data;
  },
  fulfillRequirement: async (engagementId: string, reqId: string, payload: RequirementFulfill) => {
    const { data } = await api.patch<RequirementRequestResponse>(`/auditease/engagements/${engagementId}/requirement-requests/${reqId}/fulfill`, payload);
    return data;
  },

  // Queries
  getQueries: async (engagementId: string) => {
    const { data } = await api.get<QueryResponse[]>(`/auditease/engagements/${engagementId}/queries`);
    return data;
  },
  addQueryMessage: async (engagementId: string, queryId: string, payload: QueryMessageCreate) => {
    const { data } = await api.post<QueryMessageResponse>(`/auditease/engagements/${engagementId}/queries/${queryId}/messages`, payload);
    return data;
  }
};
