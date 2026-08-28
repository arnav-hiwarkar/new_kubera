from app.services.email.client import EmailService
from app.services.email.schemas import (
    EmailAttachment,
    EmailConfig,
    EmailDeliveryError,
    EmailDeliveryResult,
    EmailMessage,
)
from app.services.email.templates import extract_plain_text, render_email_template

__all__ = [
    "EmailAttachment",
    "EmailConfig",
    "EmailDeliveryError",
    "EmailDeliveryResult",
    "EmailMessage",
    "EmailService",
    "extract_plain_text",
    "render_email_template",
]
