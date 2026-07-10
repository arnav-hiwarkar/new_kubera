export type EngagementStatus = 'invited' | 'active' | 'closed';
export type GrantStatus = 'invited' | 'accepted' | 'revoked';
export type AuditEntryStatus = 'proposed' | 'approved' | 'rejected';
export type EntryLineSide = 'debit' | 'credit';
export type RequestStatus = 'open' | 'fulfilled';
export type QueryStatus = 'open' | 'closed';
export type SenderType = 'company_user' | 'auditor';

export interface TrialBalanceAccountResponse {
  id: string;
  company_id: string;
  ledger_code: string | null;
  ledger_name: string;
  mapped_group_id: string | null;
  opening_balance: number;
  debit: number;
  credit: number;
  closing_balance: number;
  created_at: string;
  updated_at: string;
}

export interface TBImportRow {
  ledger_code: string | null;
  ledger_name: string;
  opening_balance: number;
  debit: number;
  credit: number;
  closing_balance: number;
}

export interface AuditEngagementCreate {
  period_label: string;
}

export interface AuditEngagementResponse {
  id: string;
  company_id: string;
  period_label: string;
  status: EngagementStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AuditorInvite {
  email: string;
}

export interface AuditEntryLineBase {
  ledger_id: string;
  side: EntryLineSide;
  amount: number;
}

export interface AuditEntryLineResponse extends AuditEntryLineBase {
  id: string;
  entry_id: string;
}

export interface AuditEntryCreate {
  code: string | null;
  description: string;
  lines: AuditEntryLineBase[];
}

export interface AuditEntryResponse {
  id: string;
  engagement_id: string;
  created_by: string;
  code: string | null;
  description: string;
  status: AuditEntryStatus;
  created_at: string;
  updated_at: string;
  lines: AuditEntryLineResponse[];
}

export interface RequirementRequestCreate {
  description: string;
}

export interface RequirementRequestResponse {
  id: string;
  engagement_id: string;
  raised_by: string;
  description: string;
  status: RequestStatus;
  fulfilled_document_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RequirementFulfill {
  document_id: string;
}

export interface QueryMessageCreate {
  text: string;
  attached_document_id: string | null;
}

export interface QueryMessageResponse {
  id: string;
  query_id: string;
  sender_type: SenderType;
  sender_id: string;
  text: string;
  attached_document_id: string | null;
  created_at: string;
}

export interface QueryCreate {
  initial_message: string;
  attached_document_id: string | null;
}

export interface QueryResponse {
  id: string;
  engagement_id: string;
  opened_by: string;
  status: QueryStatus;
  created_at: string;
  updated_at: string;
  messages: QueryMessageResponse[];
}

export interface EntryApproval {
  status: AuditEntryStatus;
}
