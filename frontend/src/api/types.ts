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
export type AssetResponse = S['AssetResponse'] & {
  disposal_type?: string | null
  disposal_date?: string | null
  sale_proceeds?: number | null
  buyer_name?: string | null
  disposal_invoice_no?: string | null
  disposal_remarks?: string | null
  disposal_gain_loss?: number | null
  disposal_it_proceeds?: number | null
}
export type AssetUpdate = S['AssetUpdate']
export type AssetDetailResponse = Omit<S['AssetDetailResponse'], 'asset'> & {
  asset: AssetResponse
}
export type AssetSibling = S['AssetSibling']
export type AssetQuickAddRequest = S['AssetQuickAddRequest']
export type AssetQuickAddResponse = S['AssetQuickAddResponse']
export interface AssetExistingCreate {
  asset_name: string
  category_path: string[]
  original_cost: string
  purchase_date?: string | null
  put_to_use_date?: string | null
  capitalization_date?: string | null
  opening_accumulated_depreciation?: string | null
  opening_wdv?: string | null
  opening_it_wdv?: string | null
  useful_life_months?: number | null
  useful_life_override_reason?: string | null
  residual_pct?: string | null
  branch_id?: string | null
  location_id?: string | null
  department_id?: string | null
  cost_centre_id?: string | null
  custodian_name?: string | null
  serial_number?: string | null
  remarks?: string | null
}
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

/** Live verdict on who a master edit will affect; not part of the generated schema yet. */
export interface ImpactPreview {
  kind: string
  id: string
  assets_referencing: number
  draft_run_fy_labels: string[]
  finalized_run_fy_labels: string[]
  classification: 'none' | 'future_only'
  message: string
}

export type ImpactKind = 'category' | 'it_block' | 'supplier' | 'lookup'

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
export type MeetingRecordUpdate = S['MeetingRecordUpdate']
export type BucketRefResponse = S['BucketRefResponse']
export type UnsyncedDocumentResponse = S['UnsyncedDocumentResponse']
export type SyncResultResponse = S['SyncResultResponse']

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
export type EngagementAuditorResponse = S['EngagementAuditorResponse']
export type AuditorInviteCreate = S['AuditorInviteCreate']
export type AuditorPermissionsUpdate = S['AuditorPermissionsUpdate']
export type ActivityEventResponse = S['ActivityEventResponse']
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
export type TBPreviewResponse = S['TBPreviewResponse']
export type TBDiagnostics = S['TBDiagnostics']
export type TrialBalanceViewResponse = S['TrialBalanceViewResponse']
export type TBTotalsResponse = S['TBTotalsResponse']
export type TBGroupSubtotalResponse = S['TBGroupSubtotalResponse']
export type TBSignConvention = S['TBSignConvention']
export type SetSignConventionRequest = S['SetSignConventionRequest']
/** Column map sent (as JSON string) with the TB import multipart request.
 * Values are source-column header names; `ledger_code` is optional. */
export interface TBColumnMap {
  ledger_code?: string | null
  ledger_name: string
  opening_balance?: string | null
  opening_debit?: string | null
  opening_credit?: string | null
  debit?: string | null
  credit?: string | null
  closing_balance?: string | null
  closing_debit?: string | null
  closing_credit?: string | null
  decimal_style?: 'auto' | 'dot' | 'comma'
  credit_sign?: 'auto' | 'negative' | 'positive'
}
export type RequirementRequestCreate = S['RequirementRequestCreate']
export type RequirementResponseDocumentOut = S['RequirementResponseDocumentOut']
export type RequirementSubmissionOut = S['RequirementSubmissionOut']
export type RequirementRequestResponse = S['RequirementRequestResponse']
export type QueryResponse = S['QueryResponse']
export type QueryMessageResponse = S['QueryMessageResponse']

// Financial Years
export interface FinancialYearResponse {
  id: string
  company_id: string
  label: string
  start_date: string
  end_date: string
  status: 'open' | 'closed'
  closed_at?: string | null
  closed_by?: string | null
  created_at: string
  updated_at: string
}

export interface FinancialYearCreate {
  label: string
  start_date: string
  end_date: string
}

// Disposals
export interface AssetDisposalRequest {
  disposal_date: string
  disposal_type: string
  sale_proceeds: number
  buyer_name?: string | null
  disposal_invoice_no?: string | null
  disposal_remarks?: string | null
  disposal_it_proceeds?: number | null
}

// Depreciation Runs
export interface DepreciationRunResponse {
  id: string
  company_id: string
  financial_year_id: string
  financial_year_label?: string | null
  run_date: string
  status: 'draft' | 'finalized'
  finalized_at?: string | null
  finalized_by?: string | null
  notes?: string | null
  total_gross_block: number
  total_depreciation: number
  total_carrying_amount: number
  total_it_depreciation: number
  total_it_closing_wdv: number
  created_at: string
  updated_at: string
}

export interface AssetDepreciationLineResponse {
  id: string
  run_id: string
  asset_id: string
  method: string
  opening_gross_block: number
  additions: number
  disposals: number
  closing_gross_block: number
  opening_accumulated_depreciation: number
  depreciation_for_year: number
  disposal_accumulated_depreciation: number
  closing_accumulated_depreciation: number
  opening_carrying_amount: number
  closing_carrying_amount: number
  residual_value: number
  remaining_useful_life_days: number
  effective_rate_pct: number
  is_part_year: boolean
  is_disposed: boolean
  gain_loss_on_disposal?: number | null
}

export interface ItBlockDepreciationLineResponse {
  id: string
  run_id: string
  it_block_id?: string | null
  block_name: string
  prescribed_rate: number
  opening_wdv: number
  additions_more_than_180: number
  additions_less_than_180: number
  realized_from_sales: number
  balance_before_depreciation: number
  depreciation_full_rate: number
  depreciation_half_rate: number
  total_depreciation: number
  closing_wdv: number
  capital_gain_or_loss: number
  has_stcg: boolean
  has_stcl: boolean
}

// Notifications & activity
export type NotificationOut = S['NotificationOut']
export type ActivityLogOut = S['ActivityLogOut']

// Imports
export type ImportResult = S['ImportResult']


