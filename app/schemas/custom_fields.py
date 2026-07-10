import uuid
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.custom_fields import CustomFieldModule, CustomFieldType

class CustomFieldCreate(BaseModel):
    field_name: str
    field_key: str
    field_type: CustomFieldType
    is_required: bool = False
    dropdown_options: Optional[List[str]] = None
    display_order: int = 0

class CustomFieldUpdate(BaseModel):
    field_name: Optional[str] = None
    is_required: Optional[bool] = None
    dropdown_options: Optional[List[str]] = None
    display_order: Optional[int] = None

class CustomFieldResponse(BaseModel):
    id: uuid.UUID
    module: CustomFieldModule
    field_name: str
    field_key: str
    field_type: CustomFieldType
    is_required: bool
    dropdown_options: Optional[List[str]]
    display_order: int
    is_active: bool
    company_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
