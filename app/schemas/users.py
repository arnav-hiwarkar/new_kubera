import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, Field
from app.models.company import UserRole

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole
    manager_id: uuid.UUID | None = None
    designation: str | None = None
    department: str | None = None
    accessible_modules: list[str] = Field(default_factory=list)

class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    manager_id: uuid.UUID | None = None
    designation: str | None = None
    department: str | None = None
    is_active: bool | None = None
    accessible_modules: list[str] | None = None

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    manager_id: uuid.UUID | None
    designation: str | None
    department: str | None
    is_active: bool
    deleted_at: datetime | None = None
    accessible_modules: list[str]
    company_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
