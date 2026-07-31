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

// Assets — fixed asset register
export type AssetResponse = S['AssetResponse']
export type AssetUpdate = S['AssetUpdate']
export type AssetDetailResponse = S['AssetDetailResponse']
export type AssetSibling = S['AssetSibling']
export type AssetQuickAddRequest = S['AssetQuickAddRequest']
export type AssetQuickAddResponse = S['AssetQuickAddResponse']
export type AssetLifecycleStatus = S['AssetLifecycleStatus']
export type AssetOperationalStatus = S['AssetOperationalStatus']
export type AssetCondition = S['AssetCondition']
export type AssetDocRole = S['AssetDocRole']
export type AssetDocumentResponse = S['AssetDocumentResponse']
export type AssetDocumentAttach = S['AssetDocumentAttach']
export type ValidationIssueResponse = S['ValidationIssueResponse']
export type TransitionRequest = S['TransitionRequest']
export type TransitionResponse = S['TransitionResponse']
export type BulkSerialRequest = S['BulkSerialRequest']
export type SerialAssignment = S['SerialAssignment']

// Acquisitions (invoice lines)
export type AcquisitionResponse = S['AcquisitionResponse']
export type AcquisitionUpdate = S['AcquisitionUpdate']
export type CostPreviewRequest = S['CostPreviewRequest']
export type CostPreviewResponse = S['CostPreviewResponse']
export type DiscountType = S['DiscountType']
export type ItcTreatment = S['ItcTreatment']

// Asset master data
export type AssetCategoryResponse = S['AssetCategoryResponse']
export type AssetCategoryCreate = S['AssetCategoryCreate']
export type AssetCategoryUpdate = S['AssetCategoryUpdate']
export type SupplierResponse = S['SupplierResponse']
export type SupplierCreate = S['SupplierCreate']
export type SupplierUpdate = S['SupplierUpdate']
export type AssetLookupResponse = S['AssetLookupResponse']
export type AssetLookupCreate = S['AssetLookupCreate']
export type AssetLookupUpdate = S['AssetLookupUpdate']
export type AssetLookupKind = S['AssetLookupKind']
export type ItAssetBlockResponse = S['ItAssetBlockResponse']
export type DepreciationMethod = S['DepreciationMethod']

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
export type BucketUpdate = S['BucketUpdate']
export type BucketAccessUpdate = S['BucketAccessUpdate']
export type BucketVisibility = S['BucketVisibility']
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
export type MappingSourceResponse = S['MappingSourceResponse']
export type MappingImportRequest = S['MappingImportRequest']
export type MappingImportResult = S['MappingImportResult']
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
