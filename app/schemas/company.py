"""Schemas for the company profile (Indian Pvt Ltd onboarding + settings)."""
import re
import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, field_validator

# Format validators for Indian statutory identifiers.
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")
CIN_RE = re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")
PINCODE_RE = re.compile(r"^[0-9]{6}$")

# Fields that must all be present for a company profile to count as complete.
REQUIRED_PROFILE_FIELDS = (
    "legal_name",
    "cin",
    "pan",
    "address_line1",
    "city",
    "state",
    "pincode",
    "contact_email",
    "contact_phone",
)


class CompanyProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    legal_name: str | None = None
    cin: str | None = None
    pan: str | None = None
    gstin: str | None = None
    tan: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    date_of_incorporation: date | None = None
    website: str | None = None
    industry: str | None = None
    profile_completed: bool = False
    has_logo: bool = False

    model_config = {"from_attributes": True}


class CompanyProfileUpdate(BaseModel):
    """Partial update — only provided fields change. Statutory identifiers are
    format-validated and normalized to uppercase when present."""
    legal_name: str | None = None
    cin: str | None = None
    pan: str | None = None
    gstin: str | None = None
    tan: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    date_of_incorporation: date | None = None
    website: str | None = None
    industry: str | None = None

    @field_validator("pan", "cin", "gstin", "tan", mode="before")
    @classmethod
    def _upper(cls, v):
        return v.strip().upper() if isinstance(v, str) and v.strip() else v

    @field_validator("pan")
    @classmethod
    def _check_pan(cls, v):
        if v and not PAN_RE.match(v):
            raise ValueError("Invalid PAN format (expected AAAAA9999A)")
        return v

    @field_validator("cin")
    @classmethod
    def _check_cin(cls, v):
        if v and not CIN_RE.match(v):
            raise ValueError("Invalid CIN format (21 characters, e.g. U12345MH2020PTC123456)")
        return v

    @field_validator("gstin")
    @classmethod
    def _check_gstin(cls, v):
        if v and not GSTIN_RE.match(v):
            raise ValueError("Invalid GSTIN format (15 characters)")
        return v

    @field_validator("pincode")
    @classmethod
    def _check_pincode(cls, v):
        if v and not PINCODE_RE.match(v.strip()):
            raise ValueError("Invalid pincode (expected 6 digits)")
        return v.strip() if isinstance(v, str) else v
