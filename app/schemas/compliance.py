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
    doc_type_id: uuid.UUID
    document_id: Optional[uuid.UUID] = None
    structured_metadata: Optional[Dict[str, Any]] = None
    record_date: Optional[date] = None

class MeetingRecordCreate(MeetingRecordBase):
    pass

class MeetingRecordResponse(MeetingRecordBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
