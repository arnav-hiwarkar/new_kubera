import uuid
from typing import Optional, Dict, Any, List
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models.sales import SalesStatus


class SalesSheetInfo(BaseModel):
    name: str
    headers: List[str]
    preview_rows: List[List[Any]]


class SalesImportInspectResponse(BaseModel):
    sheets: List[SalesSheetInfo]

class SalesRecordCreate(BaseModel):
    client_name: str
    product_service: str
    amount: float
    status: SalesStatus = SalesStatus.lead
    closing_date: Optional[date] = None
    user_id: Optional[uuid.UUID] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)

class SalesRecordUpdate(BaseModel):
    client_name: Optional[str] = None
    product_service: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[SalesStatus] = None
    closing_date: Optional[date] = None
    user_id: Optional[uuid.UUID] = None
    custom_fields: Optional[Dict[str, Any]] = None

class SalesRecordResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    client_name: str
    product_service: str
    amount: float
    status: SalesStatus
    closing_date: Optional[date]
    user_id: uuid.UUID
    custom_fields: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
