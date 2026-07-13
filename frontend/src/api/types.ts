import type { components } from './schema'

/**
 * Convenience aliases over the generated OpenAPI component schemas. These are the
 * single source of truth for request/response shapes — regenerate schema.d.ts
 * (`npm run gen:api`) whenever the backend changes and these follow automatically.
 */
type S = components['schemas']

// Auth
export type LoginRequest = S['LoginRequest']
export type TokenResponse = S['TokenResponse']
export type RefreshRequest = S['RefreshRequest']
export type AuditorRegister = S['AuditorRegister']
export type AuditorOut = S['AuditorOut']
export type CompanyUserOut = S['CompanyUserOut']

// Users
export type UserResponse = S['UserResponse']
export type UserCreate = S['UserCreate']
export type UserUpdate = S['UserUpdate']

// Custom fields
export type CustomFieldResponse = S['CustomFieldResponse']
export type CustomFieldCreate = S['CustomFieldCreate']
export type CustomFieldUpdate = S['CustomFieldUpdate']

// Assets
export type AssetResponse = S['AssetResponse']
export type AssetCreate = S['AssetCreate']


export type AssetUpdate = S['AssetUpdate']
export type AssetImportInspectResponse = S['AssetImportInspectResponse']
export type AssetSheetInfo = S['AssetSheetInfo']

// Sales
export type SalesRecordResponse = S['SalesRecordResponse']
export type SalesRecordCreate = S['SalesRecordCreate']
export type SalesRecordUpdate = S['SalesRecordUpdate']
export type SalesImportInspectResponse = S['SalesImportInspectResponse']
export type SalesSheetInfo = S['SalesSheetInfo']

// KRA
export type KRAResponse = S['KRAResponse']
export type KRACreate = S['KRACreate']
export type KRAUpdate = S['KRAUpdate']

// DocVault
export type BucketResponse = S['BucketResponse']
export type BucketCreate = S['BucketCreate']
export type DocumentResponse = S['DocumentResponse']
export type DocumentUpdate = S['DocumentUpdate']
export type DocumentVersionResponse = S['DocumentVersionResponse']

// Compliance (ROC + Secretarial)
export type DocumentTypeResponse = S['DocumentTypeResponse']
export type DocumentTypeCreate = S['DocumentTypeCreate']
export type MeetingRecordResponse = S['MeetingRecordResponse']
export type MeetingRecordCreate = S['MeetingRecordCreate']

// AuditEase (company + auditor)
export type AuditEngagementResponse = S['AuditEngagementResponse']
export type AuditEngagementCreate = S['AuditEngagementCreate']
export type AuditEntryResponse = S['AuditEntryResponse']
export type AuditEntryLineResponse = S['AuditEntryLineResponse']
export type AuditEntryCreate = S['AuditEntryCreate']
export type EntryApproval = S['EntryApproval']
// Report preview (Balance Sheet + P&L + entries summary)
export type ReportPreviewResponse = S['ReportPreviewResponse']
export type ReportLine = S['ReportLine']
export type ReportEntrySummary = S['ReportEntrySummary']
export type AuditorInvite = S['AuditorInvite']
export type TrialBalanceAccountResponse = S['TrialBalanceAccountResponse']
export type LedgerGroupResponse = S['LedgerGroupResponse']
export type LedgerGroupCreate = S['LedgerGroupCreate']
export type LedgerGroupRename = S['LedgerGroupRename']
export type MapLedgerRequest = S['MapLedgerRequest']
export type BulkMapRequest = S['BulkMapRequest']
export type UnmapRequest = S['UnmapRequest']
export type TBInspectResponse = S['TBInspectResponse']
export type TBSheetInfo = S['TBSheetInfo']
export type TBImportResult = S['TBImportResult']
/** Column map sent (as JSON string) with the TB import multipart request.
 * Values are source-column header names; `ledger_code` is optional. */
export interface TBColumnMap {
  ledger_code?: string | null
  ledger_name: string
  opening_balance: string
  debit: string
  credit: string
  closing_balance: string
}
export type RequirementRequestResponse = S['RequirementRequestResponse']
export type RequirementRequestCreate = S['RequirementRequestCreate']
export type RequirementFulfill = S['RequirementFulfill']
export type QueryResponse = S['QueryResponse']
export type QueryMessageResponse = S['QueryMessageResponse']

// Notifications & activity
export type NotificationOut = S['NotificationOut']
export type ActivityLogOut = S['ActivityLogOut']

// Imports
export type ImportResult = S['ImportResult']
