import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.models.lead import LeadStatus


class LeadInterestRequest(BaseModel):
    email: EmailStr
    company_name: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = Field(None, max_length=30)
    entities_count: Optional[int] = Field(None, ge=1, le=100)
    notes: Optional[str] = Field(None, max_length=1000)
    website_url_hp: Optional[str] = None  # Anti-spam honeypot (must be empty)


class LeadInterestResponse(BaseModel):
    status: str = "received"
    message: str = "Thank you for your interest in Kubera. Our team will contact you shortly."


class LeadOut(BaseModel):
    id: uuid.UUID
    email: str
    company_name: Optional[str]
    phone: Optional[str]
    entities_count: Optional[int]
    notes: Optional[str]
    status: LeadStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadStatusUpdate(BaseModel):
    status: LeadStatus


class LeadProvisionResponse(BaseModel):
    lead_id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    admin_email: str
    activation_key: str
    activation_expires_at: Optional[datetime] = None
