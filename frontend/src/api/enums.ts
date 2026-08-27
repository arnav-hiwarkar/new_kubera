import type { components } from './schema'

type S = components['schemas']

/**
 * Runtime enum values, mirroring the string enums in the backend models
 * (app/models/*.py). Kept as `as const` arrays so they double as dropdown/filter
 * option sources. The `satisfies` checks fail the build if the backend enum and
 * this list ever drift.
 */
export const ASSET_LIFECYCLE_STATUS = ['draft', 'ready', 'capitalized', 'disposed'] as const
export const ASSET_OPERATIONAL_STATUS = ['in_use', 'idle', 'under_maintenance', 'in_storage'] as const
export const ASSET_CONDITION = ['new', 'good', 'fair', 'poor', 'unusable'] as const
export const ASSET_LOOKUP_KIND = ['branch', 'cost_centre', 'department', 'location'] as const
export const DEPRECIATION_METHOD = ['slm', 'wdv'] as const
export const ITC_TREATMENT = ['eligible', 'blocked', 'partial'] as const
export const DISCOUNT_TYPE = ['amount', 'percent'] as const
export const ASSET_DOC_ROLE = [
  'invoice',
  'purchase_order',
  'grn',
  'eway_bill',
  'approval',
  'asset_photo',
  'serial_photo',
  'warranty',
  'insurance',
  'amc',
  'test_certificate',
  'manual',
  'customs',
  'lease',
  'other',
] as const
export const AUDIT_ENTRY_STATUS = ['proposed', 'approved', 'rejected'] as const
export const COMPLIANCE_DOMAIN = ['secretarial', 'roc'] as const
export const CUSTOM_FIELD_MODULE = ['asset_management', 'sales_tracking'] as const
export const CUSTOM_FIELD_TYPE = ['text', 'number', 'date', 'dropdown'] as const
export const DOCUMENT_STATUS = [
  'uploaded',
  'pending_approval',
  'action_required',
  'verified',
  'submitted',
  'overdue',
  'archived',
] as const
export const ENGAGEMENT_STATUS = ['draft', 'invited', 'active', 'closed'] as const
export const ENTRY_LINE_SIDE = ['debit', 'credit'] as const
export const KRA_STATUS = [
  'draft',
  'pending_approval',
  'approved',
  'in_progress',
  'review_submitted',
  'completed',
  'rejected',
] as const
export const QUERY_STATUS = ['open', 'closed'] as const
export const REQUEST_STATUS = ['open', 'closed'] as const
export const SALES_STATUS = ['lead', 'negotiation', 'won', 'lost'] as const
export const SENDER_TYPE = ['company_user', 'auditor'] as const
export const USER_ROLE = ['admin', 'manager', 'employee'] as const

// Compile-time guard: these arrays must stay assignable to the generated enum types.
const _guards = {
  a: ASSET_LIFECYCLE_STATUS satisfies readonly S['AssetLifecycleStatus'][],
  b: ASSET_OPERATIONAL_STATUS satisfies readonly S['AssetOperationalStatus'][],
  b1: ASSET_CONDITION satisfies readonly S['AssetCondition'][],
  b2: ASSET_LOOKUP_KIND satisfies readonly S['AssetLookupKind'][],
  b3: DEPRECIATION_METHOD satisfies readonly S['DepreciationMethod'][],
  b4: ITC_TREATMENT satisfies readonly S['ItcTreatment'][],
  b5: DISCOUNT_TYPE satisfies readonly S['DiscountType'][],
  b6: ASSET_DOC_ROLE satisfies readonly S['AssetDocRole'][],
  c: AUDIT_ENTRY_STATUS satisfies readonly S['AuditEntryStatus'][],
  d: COMPLIANCE_DOMAIN satisfies readonly S['ComplianceDomain'][],
  e: CUSTOM_FIELD_MODULE satisfies readonly S['CustomFieldModule'][],
  f: CUSTOM_FIELD_TYPE satisfies readonly S['CustomFieldType'][],
  g: DOCUMENT_STATUS satisfies readonly S['DocumentStatus'][],
  h: ENGAGEMENT_STATUS satisfies readonly S['EngagementStatus'][],
  i: ENTRY_LINE_SIDE satisfies readonly S['EntryLineSide'][],
  j: KRA_STATUS satisfies readonly S['KRAStatus'][],
  k: QUERY_STATUS satisfies readonly S['QueryStatus'][],
  l: REQUEST_STATUS satisfies readonly S['RequestStatus'][],
  m: SALES_STATUS satisfies readonly S['SalesStatus'][],
  n: SENDER_TYPE satisfies readonly S['SenderType'][],
  o: USER_ROLE satisfies readonly S['UserRole'][],
}
void _guards

export type UserRole = S['UserRole']

/** Semantic tones used by StatusBadge — mapped to design-token colors in the component. */
export type BadgeTone = 'neutral' | 'info' | 'warning' | 'success' | 'danger' | 'special'

/**
 * Status-value → tone map, derived from the backend status enums. Any status
 * string across every module resolves here; unknown values fall back to neutral.
 */
export const STATUS_TONE: Record<string, BadgeTone> = {
  // DocumentStatus
  uploaded: 'info',
  pending_approval: 'warning',
  action_required: 'danger',
  verified: 'success',
  submitted: 'special',
  overdue: 'danger',
  archived: 'neutral',
  // EngagementStatus
  invited: 'warning',
  active: 'success',
  closed: 'neutral',
  // AuditEntryStatus
  proposed: 'warning',
  approved: 'success',
  rejected: 'danger',
  // KRAStatus (adds: draft, in_progress, review_submitted, completed)
  draft: 'neutral',
  in_progress: 'special',
  review_submitted: 'warning',
  completed: 'success',
  // SalesStatus
  lead: 'info',
  negotiation: 'warning',
  won: 'success',
  lost: 'danger',
  // AssetLifecycleStatus — draft/approved covered above; the register adds these.
  ready: 'warning',
  capitalized: 'success',
  disposed: 'neutral',
  // AssetOperationalStatus
  in_use: 'success',
  idle: 'neutral',
  under_maintenance: 'warning',
  in_storage: 'info',
  // AssetCondition
  new: 'success',
  good: 'success',
  fair: 'warning',
  poor: 'danger',
  unusable: 'danger',
  maintenance: 'warning',
  // UserRole (rendered as role chips)
  admin: 'info',
  manager: 'special',
  employee: 'neutral',
}

/** Human-friendly label for an enum value (snake_case → Title Case). */
export function humanize(value: string): string {
  return value
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
