import uuid
from pydantic import BaseModel, EmailStr


# === Company ===

class CompanyUserCreate(BaseModel):
    email: EmailStr
    password: str


class CompanyCreateRequest(BaseModel):
    name: str
    admin: CompanyUserCreate


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


class CompanyWithAdmin(BaseModel):
    company: CompanyOut
    admin: CompanyUserOut


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
