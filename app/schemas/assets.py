import uuid
from typing import Optional, Dict, Any, List
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models.assets import AssetCategory, AssetStatus

class AssetCreate(BaseModel):
    asset_name: str
    serial_number: Optional[str] = None
    category: AssetCategory
    status: AssetStatus = AssetStatus.active
    purchase_date: Optional[date] = None
    purchase_cost: Optional[float] = None
    depreciation_rate: Optional[float] = None
    custodian_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)

class AssetUpdate(BaseModel):
    asset_name: Optional[str] = None
    serial_number: Optional[str] = None
    category: Optional[AssetCategory] = None
    status: Optional[AssetStatus] = None
    purchase_date: Optional[date] = None
    purchase_cost: Optional[float] = None
    depreciation_rate: Optional[float] = None
    custodian_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None
    custom_fields: Optional[Dict[str, Any]] = None

class AssetSheetInfo(BaseModel):
    name: str
    headers: List[str]
    preview_rows: List[List[Any]]


class AssetImportInspectResponse(BaseModel):
    sheets: List[AssetSheetInfo]


class AssetResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    asset_name: str
    serial_number: Optional[str]
    category: AssetCategory
    status: AssetStatus
    purchase_date: Optional[date]
    purchase_cost: Optional[float]
    depreciation_rate: Optional[float]
    custodian_id: Optional[uuid.UUID]
    document_id: Optional[uuid.UUID]
    custom_fields: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
