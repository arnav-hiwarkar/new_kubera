import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator

from app.models.auditease import (
    EngagementStatus, GrantStatus, AuditEntryStatus, EntryLineSide, RequestStatus,
    QueryStatus, SenderType, BalanceNature, TBSignConvention,
)


# --- Ledger & Trial Balance ---

class LedgerGroupResponse(BaseModel):
    id: uuid.UUID
    company_id: Optional[uuid.UUID]
    parent_id: Optional[uuid.UUID]
    name: str
    level: int
    has_children: bool
    # Natural side, inherited from the level-0 ancestor. Lets the mapping UI show
    # Dr/Cr per head so the sign convention is legible to the user.
    nature: Optional[BalanceNature] = None
    model_config = {"from_attributes": True}

class LedgerGroupCreate(BaseModel):
    name: str
    parent_id: uuid.UUID  # top groups are seeded/read-only; a new group always has a parent

class LedgerGroupRename(BaseModel):
    name: str

class MapLedgerRequest(BaseModel):
    group_id: uuid.UUID

class BulkMapRequest(BaseModel):
    ledger_ids: List[uuid.UUID]
    group_id: uuid.UUID

class UnmapRequest(BaseModel):
    ledger_ids: List[uuid.UUID]

class MappingSourceResponse(BaseModel):
    engagement_id: uuid.UUID
    period_label: str
    status: EngagementStatus
    total_ledger_count: int
    mapped_ledger_count: int

class MappingImportRequest(BaseModel):
    source_engagement_id: uuid.UUID
    overwrite_existing: bool = True

class MappingImportIssue(BaseModel):
    target_ledger_id: uuid.UUID
    ledger_code: Optional[str] = None
    ledger_name: str
    reason: Literal[
        "unmatched",
        "source_exhausted",
        "identity_disagreement",
        "ambiguous_source_mapping",
    ]

class MappingImportResult(BaseModel):
    total_target_ledgers: int
    source_mapped_count: int
    assigned_count: int
    updated_count: int
    already_correct_count: int
    preserved_existing_count: int
    unused_source_count: int
    unresolved_count: int
    issues: List[MappingImportIssue]

class TrialBalanceAccountBase(BaseModel):
    ledger_code: Optional[str] = None
    ledger_name: str
    mapped_group_id: Optional[uuid.UUID] = None
    mapped_group_name: Optional[str] = None
    parent_group_name: Optional[str] = None
    top_group_name: Optional[str] = None
    # As-imported source figures. Kept for the audit trail; NOT used for accounting.
    opening_balance: float = 0
    debit: float = 0
    credit: float = 0
    closing_balance: float = 0

class TrialBalanceAccountResponse(TrialBalanceAccountBase):
    id: uuid.UUID
    company_id: uuid.UUID
    engagement_id: uuid.UUID
    # Resolved group path root→leaf (e.g. ["Assets", "Current Assets", "Cash"]), for display.
    mapped_group_path: Optional[List[str]] = None
    # --- canonical signed net debit: the figures the statements are built from ---
    opening_net_debit: float = 0
    closing_net_debit: float = 0
    adjustment_net_debit: float = 0
    final_net_debit: float = 0
    presented_opening: float = 0
    presented_closing: float = 0
    presented_adjustment: float = 0
    presented_final: float = 0
    nature: Optional[BalanceNature] = None
    sign_unresolved: bool = False
    source_row_consistent: Optional[bool] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# --- Trial Balance import (inspect -> map -> preview -> import) ---

class TBSheetInfo(BaseModel):
    name: str
    headers: List[str]
    preview_rows: List[List[Any]]  # first N data rows, raw cell values as strings
    header_row: int = 1            # 1-indexed detected header row
    first_data_row: int = 2
    skipped_leading_rows: List[List[str]] = []   # title/banner rows above the header
    suggested_map: Dict[str, str] = {}


class TBInspectResponse(BaseModel):
    sheets: List[TBSheetInfo]


class TBColumnMap(BaseModel):
    """Maps each DB field to a source column header.

    Only `ledger_name` plus ONE balance source is required. The old contract
    demanded all four numeric columns, which rejected the two most common real
    layouts: a Dr/Cr pair with no closing column, and a single signed closing
    column with no movements.
    """
    ledger_code: Optional[str] = None
    ledger_name: str
    opening_balance: Optional[str] = None
    opening_debit: Optional[str] = None
    opening_credit: Optional[str] = None
    debit: Optional[str] = None
    credit: Optional[str] = None
    closing_balance: Optional[str] = None
    closing_debit: Optional[str] = None
    closing_credit: Optional[str] = None
    # How to read '.' and ',' in this file, and whether credit balances are stored
    # positive. Exposed so an EU-formatted export can be forced rather than guessed.
    decimal_style: Literal["auto", "dot", "comma"] = "auto"
    credit_sign: Literal["auto", "negative", "positive"] = "auto"

    @model_validator(mode="after")
    def _check_sufficient(self) -> "TBColumnMap":
        from app.services.trial_balance import validate_column_map
        errors = validate_column_map(self.model_dump())
        if errors:
            raise ValueError("; ".join(errors))
        return self


class TBRowIssue(BaseModel):
    row: int
    ledger_name: Optional[str] = None
    kind: Literal["error", "dropped", "warning"]
    reason: str
    raw: Optional[List[str]] = None


class TBDiagnostics(BaseModel):
    """Everything we learned about the source file. Reported, never blocking."""
    header_row: int
    rows_scanned: int
    rows_imported: int
    rows_dropped_blank: int = 0
    rows_dropped_total: int = 0
    rows_dropped_repeated_header: int = 0
    rows_section: int = 0
    rows_error: int = 0
    detected_convention: TBSignConvention
    convention_confidence: str
    convention_evidence: List[str] = []
    negative_closing_count: int = 0
    explicit_marker_count: int = 0
    derived_fields: List[str] = []
    total_debit: float = 0
    total_credit: float = 0
    debit_credit_difference: float = 0
    movement_balanced: bool = True
    closing_sum: float = 0
    closing_sums_to_zero: bool = True
    opening_sum: float = 0
    opening_sums_to_zero: bool = True
    row_consistency_mismatches: int = 0
    inconsistent_rows: List[dict] = []
    sign_unresolved_count: int = 0
    sheet_stated_total_debit: Optional[float] = None
    sheet_stated_total_credit: Optional[float] = None
    issues: List[TBRowIssue] = []           # capped by the router


class TBParsedRow(BaseModel):
    row: int
    ledger_name: str
    opening_balance: float
    debit: float
    credit: float
    closing_balance: float
    closing_net_debit: float
    derived: List[str] = []
    notes: List[str] = []


class TBReimportImpact(BaseModel):
    """What a re-import would do, so the user confirms instead of being refused."""
    existing_ledger_count: int
    approved_entry_count: int
    proposed_entry_count: int
    mapped_ledger_count: int
    matched_by_code: int
    matched_by_name: int
    new_ledger_count: int
    will_lose_mapping: List[str] = []
    retained_referenced: List[str] = []
    ambiguous_matches: List[str] = []
    requires_confirmation: bool = False


class TBPreviewResponse(BaseModel):
    diagnostics: TBDiagnostics
    sample_rows: List[TBParsedRow]
    reimport_impact: Optional[TBReimportImpact] = None
    would_import: int
    would_skip: int


class TBGroupSubtotalResponse(BaseModel):
    key: str
    nature: Optional[BalanceNature] = None
    opening_net_debit: float = 0
    presented_opening: float = 0
    debit: float = 0
    credit: float = 0
    closing_net_debit: float = 0
    presented_closing: float = 0
    adjustment_net_debit: float = 0
    presented_adjustment: float = 0
    final_net_debit: float = 0
    presented_final: float = 0
    net_debit: float
    presented: float
    ledger_count: int


class TBTotalsResponse(BaseModel):
    """The single authoritative totals shape.

    Computed server-side by trial_balance.summarize and consumed verbatim by the
    trial-balance grid, the balance card and the reports tab, so those three can
    never disagree. `difference` is the one and only definition of "balanced":
    the sum of every mapped ledger's signed net debit.
    """
    groups: List[TBGroupSubtotalResponse] = []
    assets: float
    liabilities: float
    income: float
    expenditure: float
    equity: float
    net_profit: float
    liabilities_plus_equity: float
    difference: float
    difference_including_unmapped: float
    balanced: bool
    unmapped_net_debit: float
    unmapped_count: int
    unresolved_nature_count: int
    sign_unresolved_count: int
    ledger_count: int
    mapped_count: int
    statement_ready: bool
    total_debit: float
    total_credit: float
    movement_balanced: bool


class TrialBalanceViewResponse(BaseModel):
    accounts: List[TrialBalanceAccountResponse]
    totals: TBTotalsResponse
    sign_convention: Optional[TBSignConvention] = None
    sign_unresolved_count: int = 0
    inconsistent_row_count: int = 0
    warnings: List[str] = []


class SetSignConventionRequest(BaseModel):
    convention: TBSignConvention

    @model_validator(mode="after")
    def _repairable_convention(self) -> "SetSignConventionRequest":
        if self.convention not in (TBSignConvention.signed, TBSignConvention.magnitude):
            raise ValueError("only signed or magnitude can be selected manually")
        return self


class TBImportResult(BaseModel):
    imported: int
    skipped: int
    errors: List[dict]
    # Movement totals off the source Dr/Cr columns. Retained for back-compat; the
    # authoritative balance answer is `totals.balanced` / `diagnostics.closing_sums_to_zero`.
    total_debit: float
    total_credit: float
    balanced: bool
    accounts: List[TrialBalanceAccountResponse]
    diagnostics: Optional[TBDiagnostics] = None
    sign_convention: Optional[TBSignConvention] = None
    totals: Optional[TBTotalsResponse] = None


# --- Engagements ---

class AuditEngagementBase(BaseModel):
    period_label: str

class AuditEngagementCreate(AuditEngagementBase):
    pass

class AuditEngagementResponse(AuditEngagementBase):
    id: uuid.UUID
    company_id: uuid.UUID
    status: EngagementStatus
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Populated by the company-side router for the single invited/accepted auditor.
    # grant status is one of: invited | accepted | revoked | pending (not yet registered)
    auditor_email: Optional[str] = None
    auditor_grant_status: Optional[str] = None
    model_config = {"from_attributes": True}

class AuditorEngagementGrantResponse(BaseModel):
    id: uuid.UUID
    auditor_id: uuid.UUID
    engagement_id: uuid.UUID
    status: GrantStatus
    invited_at: datetime
    accepted_at: Optional[datetime]
    model_config = {"from_attributes": True}


# --- Entries ---

class AuditEntryLineBase(BaseModel):
    ledger_id: uuid.UUID
    side: EntryLineSide
    amount: float

class AuditEntryLineResponse(AuditEntryLineBase):
    id: uuid.UUID
    entry_id: uuid.UUID
    # Flattened from the related trial-balance account so both the auditor and
    # company UIs can show which ledger a line adjusts.
    ledger_name: str
    ledger_code: Optional[str] = None
    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _flatten_ledger(cls, data):
        # `data` is the ORM AuditEntryLine on the read path. Surface the ledger's
        # name/code as flat fields; the relationship is eager-loaded by callers.
        if isinstance(data, dict):
            return data
        ledger = getattr(data, "ledger", None)
        values = {
            "id": data.id,
            "entry_id": data.entry_id,
            "ledger_id": data.ledger_id,
            "side": data.side,
            "amount": data.amount,
            "ledger_name": getattr(ledger, "ledger_name", None) or "(deleted ledger)",
            "ledger_code": getattr(ledger, "ledger_code", None),
        }
        return values

class AuditEntryCreate(BaseModel):
    code: Optional[str] = None
    description: str
    lines: List[AuditEntryLineBase]

class AuditEntryResponse(BaseModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    created_by: uuid.UUID
    code: Optional[str]
    description: str
    status: AuditEntryStatus
    rejection_comment: Optional[str]
    created_at: datetime
    updated_at: datetime
    lines: List[AuditEntryLineResponse]
    model_config = {"from_attributes": True}


# --- Requests & Queries ---

class RequirementRequestCreate(BaseModel):
    description: str
    title: Optional[str] = None

class RequirementRequestResponse(BaseModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    raised_by: uuid.UUID
    title: str
    description: str
    status: RequestStatus
    fulfilled_document_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class QueryMessageCreate(BaseModel):
    text: str
    attached_document_id: Optional[uuid.UUID] = None

class QueryMessageResponse(BaseModel):
    id: uuid.UUID
    query_id: uuid.UUID
    sender_type: SenderType
    sender_id: uuid.UUID
    text: str
    attached_document_id: Optional[uuid.UUID]
    created_at: datetime
    model_config = {"from_attributes": True}

class QueryCreate(BaseModel):
    initial_message: str
    attached_document_id: Optional[uuid.UUID] = None

class QueryResponse(BaseModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    opened_by: uuid.UUID
    status: QueryStatus
    created_at: datetime
    updated_at: datetime
    messages: List[QueryMessageResponse] = []
    model_config = {"from_attributes": True}


# --- Reports ---

class ReportLine(BaseModel):
    """One ledger's contribution to the statements, with audit adjustments applied.

    `closing`/`adjustment`/`final` are PRESENTED figures -- already oriented onto the
    group's natural side -- so `closing + adjustment == final` holds on every row,
    including unmapped ones. `net_debit` is the underlying canonical value.
    """
    # None for the synthetic "Profit for the period" balancing line.
    ledger_id: Optional[uuid.UUID] = None
    ledger_name: str
    ledger_code: Optional[str] = None
    # Top-level Schedule III group: Assets | Liabilities | Income | Expenditure | None
    top_group: Optional[str] = None
    group_path: Optional[List[str]] = None
    nature: Optional[BalanceNature] = None
    closing: float
    adjustment: float
    final: float
    net_debit: float = 0
    sign_unresolved: bool = False
    is_synthetic: bool = False

class ReportTotals(BaseModel):
    assets: float
    liabilities: float
    income: float
    expenditure: float
    equity: float = 0
    other_liabilities: float = 0
    groups: List[TBGroupSubtotalResponse] = []

class ReportBalanceCheck(BaseModel):
    assets: float
    liabilities_plus_equity: float
    difference: float
    balanced: bool
    statement_ready: bool = False
    # An unmapped ledger cannot be placed on a statement, so it is excluded from
    # `difference`. Surfaced separately because an unmapped non-zero balance is
    # exactly why a trial balance that does balance can produce statements that don't.
    unmapped_net_debit: float = 0
    difference_including_unmapped: float = 0

class ReportEntrySummary(BaseModel):
    id: uuid.UUID
    code: Optional[str] = None
    description: str
    total: float
    line_count: int

class ReportEntriesBlock(BaseModel):
    approved: List[ReportEntrySummary]
    approved_count: int
    proposed_count: int

class ReportPreviewResponse(BaseModel):
    period_label: str
    lines: List[ReportLine]
    totals: ReportTotals
    net_profit: float
    balance_check: ReportBalanceCheck
    entries: ReportEntriesBlock
    unmapped_count: int
    unresolved_nature_count: int = 0
    sign_convention: Optional[TBSignConvention] = None
    # Conditions that make the statements untrustworthy but are not errors, e.g. an
    # approved entry adjusting an unmapped ledger (only one leg reaches the totals).
    warnings: List[str] = []


class ReportTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    schema_content: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
