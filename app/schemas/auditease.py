import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from app.models.auditease import EngagementStatus, GrantStatus, AuditEntryStatus, EntryLineSide, RequestStatus, QueryStatus, SenderType


# --- Ledger & Trial Balance ---

class LedgerGroupBase(BaseModel):
    name: str
    parent_id: Optional[uuid.UUID] = None
    has_children: bool = False

class LedgerGroupCreate(LedgerGroupBase):
    pass

class LedgerGroupResponse(LedgerGroupBase):
    id: uuid.UUID
    company_id: Optional[uuid.UUID]
    model_config = {"from_attributes": True}

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
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


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
    model_config = {"from_attributes": True}

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

class ReportTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    schema_content: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
