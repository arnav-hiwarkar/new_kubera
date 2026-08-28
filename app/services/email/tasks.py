import smtplib
from typing import Any, Dict, Optional
from app.services.email.client import EmailService
from app.services.email.schemas import EmailConfig, EmailMessage
from app.worker import celery_app


@celery_app.task(
    name="app.services.email.tasks.send_email_async",
    autoretry_for=(smtplib.SMTPException, OSError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def send_email_async(message_dict: Dict[str, Any], config_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Celery background task for asynchronous email delivery with automatic retries."""
    config = EmailConfig(**config_dict) if config_dict else None
    message = EmailMessage(**message_dict)
    service = EmailService(config=config)
    result = service.send(message)
    return result.model_dump()
