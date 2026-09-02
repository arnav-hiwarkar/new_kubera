"""Pydantic schemas for Financial Year management."""
import uuid
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator


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


class FinancialYearReopenRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        trimmed = v.strip()
        if len(trimmed) < 10:
            raise ValueError("Reason must be at least 10 characters long after trimming whitespace")
        return trimmed
