import uuid
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.models.kra import KRAStatus

class KRACreate(BaseModel):
    title: str
    description: str
    weightage: float = 0.0
    target_metric: Optional[str] = None
    cycle: str
    user_id: Optional[uuid.UUID] = None

class KRAUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    weightage: Optional[float] = None
    target_metric: Optional[str] = None
    status: Optional[KRAStatus] = None
    employee_self_rating: Optional[float] = None
    employee_comment: Optional[str] = None
    manager_rating: Optional[float] = None
    manager_comment: Optional[str] = None
    rejection_reason: Optional[str] = None

class KRAResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    title: str
    description: str
    weightage: float
    target_metric: Optional[str]
    cycle: str
    status: KRAStatus
    user_id: uuid.UUID
    manager_id: Optional[uuid.UUID]
    employee_self_rating: Optional[float]
    employee_comment: Optional[str]
    manager_rating: Optional[float]
    manager_comment: Optional[str]
    rejection_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
