import logging
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.encryption import decrypt_company_kek, decrypt_smtp_password
from app.models.company import CompanyKey
from app.models.company_smtp import CompanySmtpConfig, EmailLog
from app.services.email.client import EmailService
from app.services.email.schemas import EmailConfig

logger = logging.getLogger(__name__)


async def get_company_kek(db: AsyncSession, company_id: uuid.UUID) -> bytes:
    key = (
        await db.execute(select(CompanyKey).where(CompanyKey.company_id == company_id))
    ).scalar_one_or_none()
    if key is None:
        raise ValueError(f"CompanyKey not found for company {company_id}")
    return decrypt_company_kek(key.encrypted_kek, key.kek_nonce)


async def get_email_config_for_company(
    db: AsyncSession, company_id: uuid.UUID
) -> Optional[EmailConfig]:
    """Retrieve decrypted EmailConfig for a company, or None if unconfigured/inactive."""
    res = await db.execute(
        select(CompanySmtpConfig).where(
            CompanySmtpConfig.company_id == company_id,
            CompanySmtpConfig.is_active.is_(True),
        )
    )
    smtp_row = res.scalar_one_or_none()
    if not smtp_row:
        return None

    try:
        kek = await get_company_kek(db, company_id)
        raw_password = decrypt_smtp_password(smtp_row.encrypted_password, smtp_row.password_nonce, kek)
        return EmailConfig(
            host=smtp_row.host,
            port=smtp_row.port,
            user=smtp_row.user,
            password=raw_password,
            use_tls=smtp_row.use_tls,
            use_ssl=smtp_row.use_ssl,
            from_email=smtp_row.from_email,
            from_name=smtp_row.from_name,
        )
    except Exception as e:
        logger.error(f"Failed to decrypt SMTP credentials for company {company_id}: {e}")
        return None


async def get_email_service_for_company(
    db: AsyncSession, company_id: uuid.UUID
) -> EmailService:
    """Return an EmailService instance configured for the company, falling back to server default."""
    config = await get_email_config_for_company(db, company_id)
    return EmailService(config=config)


async def record_email_log(
    db: AsyncSession,
    sender_email: str,
    sender_name: str,
    recipient_email: str,
    subject: str,
    template_name: str,
    status: str,
    source: str,
    company_id: Optional[uuid.UUID] = None,
    message_id: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> EmailLog:
    """Record an audit trail entry for dispatched email."""
    log_entry = EmailLog(
        company_id=company_id,
        sender_email=sender_email,
        sender_name=sender_name,
        recipient_email=recipient_email,
        subject=subject,
        template_name=template_name,
        status=status,
        message_id=message_id,
        error_message=error_message,
        duration_ms=duration_ms,
        source=source,
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)
    return log_entry
