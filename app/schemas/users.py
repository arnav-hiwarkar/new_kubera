import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, Field, computed_field
from app.models.company import UserRole

class UserChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole
    manager_id: uuid.UUID | None = None
    designation: str | None = None
    department: str | None = None
    accessible_modules: list[str] = Field(default_factory=list)
    can_change_password: bool = True

class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    manager_id: uuid.UUID | None = None
    designation: str | None = None
    department: str | None = None
    is_active: bool | None = None
    accessible_modules: list[str] | None = None
    can_change_password: bool | None = None

class UserResponse(BaseModel):
    id: uuid.UUID
    # Plain str (not EmailStr): output never needs email validation, and a
    # soft-deleted/legacy row could hold a non-RFC address — validating it here
    # would 500 the entire list response.
    email: str
    full_name: str
    role: UserRole
    manager_id: uuid.UUID | None
    designation: str | None
    department: str | None
    is_active: bool
    deleted_at: datetime | None = None
    accessible_modules: list[str]
    company_id: uuid.UUID
    can_change_password: bool = True
    avatar_updated_at: datetime | None = None
    password_changed_at: datetime | None = None
    avatar_path: str | None = Field(default=None, exclude=True)
    created_at: datetime

    @computed_field
    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar_path)

    model_config = ConfigDict(from_attributes=True)

