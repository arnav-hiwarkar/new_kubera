import uuid
from datetime import datetime, date
from typing import Optional, Dict, Any
from pydantic import BaseModel

from app.models.compliance import ComplianceDomain

class DocumentTypeBase(BaseModel):
    name: str
    template_file_id: Optional[uuid.UUID] = None
    metadata_schema: Optional[Dict[str, Any]] = None
    due_date_rule: Optional[str] = None

class DocumentTypeCreate(DocumentTypeBase):
    pass

class DocumentTypeResponse(DocumentTypeBase):
    id: uuid.UUID
    company_id: Optional[uuid.UUID]
    domain: ComplianceDomain
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class MeetingRecordBase(BaseModel):
    # Optional so a record can be staged (or imported from docVault) before anyone
    # decides what it is; the details are filled in later via PATCH.
    doc_type_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    structured_metadata: Optional[Dict[str, Any]] = None
    record_date: Optional[date] = None

class MeetingRecordCreate(MeetingRecordBase):
    pass

class MeetingRecordUpdate(BaseModel):
    """Partial update. The router applies it with exclude_unset, so an omitted
    field is left alone while an explicit null clears it."""
    doc_type_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    structured_metadata: Optional[Dict[str, Any]] = None
    record_date: Optional[date] = None

class MeetingRecordResponse(MeetingRecordBase):
    id: uuid.UUID
    company_id: uuid.UUID
    domain: ComplianceDomain
    # Set when archived. archived_document_status is an internal restore detail and
    # is deliberately not exposed.
    archived_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class BucketRefResponse(BaseModel):
    """The docVault bucket this compliance domain files its documents into."""
    id: uuid.UUID
    name: str

class UnsyncedDocumentResponse(BaseModel):
    """A docVault document sitting in the domain's bucket with no record yet."""
    id: uuid.UUID
    title: str
    original_filename: Optional[str] = None
    size_bytes: Optional[int] = None
    uploaded_at: Optional[datetime] = None

class SyncResultResponse(BaseModel):
    imported: int
    records: list[MeetingRecordResponse]
