import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from app.models.docvault import DocumentStatus


class BucketCreate(BaseModel):
    name: str = Field(..., max_length=255)


class BucketResponse(BaseModel):
    id: uuid.UUID
    name: str
    company_id: uuid.UUID
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum: str
    uploaded_by: Optional[uuid.UUID]
    uploaded_at: datetime
    version_number: int

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    current_version_id: Optional[uuid.UUID]
    bucket_id: Optional[uuid.UUID]
    status: DocumentStatus
    title: str
    doc_type_id: Optional[uuid.UUID]
    tags: List[str]
    is_editable: bool
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    versions: List[DocumentVersionResponse] = []

    model_config = {"from_attributes": True}


class DocumentUpdate(BaseModel):
    status: Optional[DocumentStatus] = None
    bucket_id: Optional[uuid.UUID] = None
    tags: Optional[List[str]] = None
    is_editable: Optional[bool] = None
