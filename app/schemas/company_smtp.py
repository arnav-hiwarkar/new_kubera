from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.services.email.net_guard import ALLOWED_PORTS


class CompanySmtpConfigOut(BaseModel):
    configured: bool
    host: Optional[str] = None
    port: Optional[int] = 587
    user: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    use_tls: bool = True
    use_ssl: bool = False
    is_active: bool = True
    has_password: bool = False
    last_tested_at: Optional[datetime] = None


class CompanySmtpConfigUpdate(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=587)
    user: str = Field(min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=1)
    use_tls: bool = True
    use_ssl: bool = False
    from_email: EmailStr
    from_name: str = Field(min_length=1, max_length=255)
    is_active: bool = True

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v not in ALLOWED_PORTS:
            raise ValueError(f"Port {v} is not a permitted SMTP port ({', '.join(str(p) for p in sorted(ALLOWED_PORTS))})")
        return v


class CompanySmtpVerifyRequest(BaseModel):
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = None

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in ALLOWED_PORTS:
            raise ValueError(f"Port {v} is not a permitted SMTP port ({', '.join(str(p) for p in sorted(ALLOWED_PORTS))})")
        return v


class CompanySmtpVerifyResponse(BaseModel):
    success: bool
    host: str
    port: int
    user: str
    latency_ms: float
    message: str


class EmailLogOut(BaseModel):
    id: str
    sender_email: str
    sender_name: str
    recipient_email: str
    subject: str
    template_name: str
    status: str
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
    source: str
    created_at: datetime
