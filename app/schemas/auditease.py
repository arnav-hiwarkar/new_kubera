import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator

from app.models.auditease import EngagementStatus, GrantStatus, AuditEntryStatus, EntryLineSide, RequestStatus, QueryStatus, SenderType


# --- Ledger & Trial Balance ---

class LedgerGroupResponse(BaseModel):
    id: uuid.UUID
    company_id: Optional[uuid.UUID]
    parent_id: Optional[uuid.UUID]
    name: str
    level: int
    has_children: bool
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

class TrialBalanceAccountBase(BaseModel):
    ledger_code: Optional[str] = None
    ledger_name: str
    mapped_group_id: Optional[uuid.UUID] = None
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
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# --- Trial Balance import (server-side, two-call) ---

class TBSheetInfo(BaseModel):
    name: str
    headers: List[str]
    preview_rows: List[List[Any]]  # first N data rows, raw cell values as strings


class TBInspectResponse(BaseModel):
    sheets: List[TBSheetInfo]


class TBColumnMap(BaseModel):
    """Maps each DB field to a source column header. `ledger_code` optional."""
    ledger_code: Optional[str] = None
    ledger_name: str
    opening_balance: str
    debit: str
    credit: str
    closing_balance: str


class TBImportResult(BaseModel):
    imported: int
    skipped: int
    errors: List[dict]
    total_debit: float
    total_credit: float
    balanced: bool
    accounts: List[TrialBalanceAccountResponse]


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
    created_at: datetime
    updated_at: datetime
    lines: List[AuditEntryLineResponse]
    model_config = {"from_attributes": True}


# --- Requests & Queries ---

class RequirementRequestCreate(BaseModel):
    description: str

class RequirementRequestResponse(BaseModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    raised_by: uuid.UUID
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
    """One ledger's contribution to the statements, with audit adjustments applied."""
    ledger_id: uuid.UUID
    ledger_name: str
    ledger_code: Optional[str] = None
    # Top-level Schedule III group: Assets | Liabilities | Income | Expenditure | None
    top_group: Optional[str] = None
    group_path: Optional[List[str]] = None
    closing: float
    adjustment: float
    final: float

class ReportTotals(BaseModel):
    assets: float
    liabilities: float
    income: float
    expenditure: float

class ReportBalanceCheck(BaseModel):
    assets: float
    liabilities_plus_equity: float
    difference: float
    balanced: bool

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


class ReportTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    schema_content: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
