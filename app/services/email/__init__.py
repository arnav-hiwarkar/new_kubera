from app.services.email.client import EmailService
from app.services.email.schemas import (
    EmailAttachment,
    EmailConfig,
    EmailDeliveryError,
    EmailDeliveryResult,
    EmailMessage,
)
from app.services.email.resolver import (
    get_email_config_for_company,
    get_email_service_for_company,
    record_email_log,
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
    "get_email_config_for_company",
    "get_email_service_for_company",
    "record_email_log",
    "render_email_template",
]
