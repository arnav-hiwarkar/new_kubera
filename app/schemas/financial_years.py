"""Pydantic schemas for Financial Year management."""
import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field


class FinancialYearCreate(BaseModel):
    label: str = Field(..., max_length=50, description="e.g. 2024-25 or FY 2024-25")
    start_date: date
    end_date: date


class FinancialYearResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    label: str
    start_date: date
    end_date: date
    status: str
    closed_at: datetime | None = None
    closed_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
