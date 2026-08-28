from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EmailAttachment(BaseModel):
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


class EmailMessage(BaseModel):
    to: List[str]
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    reply_to: Optional[str] = None
    attachments: Optional[List[EmailAttachment]] = None
    template_name: Optional[str] = None
    template_context: Optional[Dict[str, Any]] = None


class EmailConfig(BaseModel):
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str = "kubera@ethdc.in"
    from_name: str = "Kubera Compliance"
    timeout: int = 15


class EmailDeliveryResult(BaseModel):
    success: bool
    message_id: str
    recipients: List[str]
    duration_ms: float
    error: Optional[str] = None


class EmailDeliveryError(Exception):
    """Raised when an email fails to send via SMTP."""
    pass
