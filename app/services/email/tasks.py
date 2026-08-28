import asyncio
import logging
import smtplib
import uuid
from typing import Any, Dict, Optional

from app.services.email.client import EmailService
from app.services.email.schemas import EmailConfig, EmailDeliveryError, EmailMessage
from app.worker import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine synchronously in a dedicated event loop for Celery workers."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def _get_worker_session_factory():
    from sqlalchemy.pool import NullPool
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


def _resolve_company_config(company_id_str: str) -> Optional[EmailConfig]:
    """Retrieve and decrypt company SMTP config directly inside the Celery worker."""
    from app.services.email.resolver import get_email_config_for_company

    async def _fetch():
        session_factory = _get_worker_session_factory()
        async with session_factory() as session:
            return await get_email_config_for_company(session, uuid.UUID(company_id_str))

    try:
        return _run_async(_fetch())
    except Exception as e:
        logger.error(f"Failed to resolve SMTP config for company {company_id_str}: {e}")
        return None


def _update_email_log(
    log_id_str: str,
    status: str,
    message_id: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """Update status, message_id, duration_ms, and error_message in EmailLog record."""
    from sqlalchemy import update
    from app.models.company_smtp import EmailLog

    async def _update():
        session_factory = _get_worker_session_factory()
        async with session_factory() as session:
            values: Dict[str, Any] = {"status": status}
            if message_id is not None:
                values["message_id"] = message_id
            if error_message is not None:
                values["error_message"] = error_message[:2000]
            if duration_ms is not None:
                values["duration_ms"] = duration_ms
            await session.execute(
                update(EmailLog).where(EmailLog.id == uuid.UUID(log_id_str)).values(**values)
            )
            await session.commit()

    try:
        _run_async(_update())
    except Exception as e:
        logger.error(f"Failed to update EmailLog {log_id_str}: {e}")


@celery_app.task(
    name="app.services.email.tasks.send_email_async",
    autoretry_for=(smtplib.SMTPException, OSError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def send_email_async(
    message_dict: Dict[str, Any],
    company_id: Optional[str] = None,
    log_id: Optional[str] = None,
    config_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Celery background task for asynchronous email delivery with automatic retries.

    Args:
        message_dict: Serialized EmailMessage dictionary.
        company_id: Optional company UUID string — worker decrypts credentials from DB.
        log_id: Optional EmailLog UUID string — worker updates delivery result.
        config_dict: Optional explicit EmailConfig dictionary (e.g. for testing / CLI).
    """
    config: Optional[EmailConfig] = None
    if config_dict:
        config = EmailConfig(**config_dict)
    elif company_id:
        config = _resolve_company_config(company_id)

    message = EmailMessage(**message_dict)
    service = EmailService(config=config)

    try:
        result = service.send(message)
    except EmailDeliveryError as e:
        err_str = str(e)
        logger.error(f"Email delivery failed: {err_str}")
        if log_id:
            _update_email_log(log_id, status="failed", error_message=err_str)

        # Permanent non-retryable errors
        if any(kw in err_str.lower() for kw in ("not configured", "authentication failed", "template")):
            return {"success": False, "error": err_str}

        # Transient errors raise for Celery retry
        raise smtplib.SMTPException(err_str) from e
    except Exception as e:
        err_str = str(e)
        logger.error(f"Unexpected error during email delivery: {err_str}")
        if log_id:
            _update_email_log(log_id, status="failed", error_message=err_str)
        raise

    if log_id:
        _update_email_log(
            log_id,
            status="sent",
            message_id=result.message_id,
            duration_ms=result.duration_ms,
        )

    return result.model_dump()
