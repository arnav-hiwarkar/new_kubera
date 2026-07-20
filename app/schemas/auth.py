import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# === Company ===

class CompanyInitRequest(BaseModel):
    """Operator-initiated company creation (internal API key gated)."""
    name: str = Field(min_length=1, max_length=255)
    admin_email: EmailStr


class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class CompanyUserOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    email: str
    role: str
    manager_id: uuid.UUID | None = None
    full_name: str = "Unknown"
    designation: str | None = None
    department: str | None = None
    is_active: bool = True
    accessible_modules: list[str] = []

    model_config = {"from_attributes": True}


class CompanyInitResponse(BaseModel):
    """Returned once at init/reissue — carries the plaintext activation key."""
    company: CompanyOut
    admin: CompanyUserOut
    activation_key: str
    activation_expires_at: datetime


class ReissueKeyResponse(BaseModel):
    activation_key: str
    activation_expires_at: datetime


class ActivationRequest(BaseModel):
    """Admin claims their account with the one-shot key and sets a password."""
    email: EmailStr
    activation_key: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)


class CompanyListItem(BaseModel):
    """Backend-only company listing row."""
    id: uuid.UUID
    name: str
    admin_email: str | None = None
    admin_active: bool = False
    profile_completed: bool = False
    activation_pending: bool = False
    activation_expires_at: datetime | None = None
    created_at: datetime
    archived: bool = False

    model_config = {"from_attributes": True}


class CompanyDeleteRequest(BaseModel):
    """Confirmation safety rail for hard delete."""
    confirm_name: str


# === Auditor ===

class AuditorRegister(BaseModel):
    email: EmailStr
    password: str
    name: str


class AuditorOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str

    model_config = {"from_attributes": True}


# === Login ===

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str | None = None
    full_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
