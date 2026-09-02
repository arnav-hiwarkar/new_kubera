from datetime import datetime, timezone
import asyncio
import logging
logger = logging.getLogger(__name__)
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.encryption import encrypt_smtp_password
from app.database import get_db
from app.models.activity_log import ActivityLog, ActorType
from app.models.company_smtp import CompanySmtpConfig, EmailLog
from app.models.company import CompanyUser
from app.schemas.company_smtp import (
    CompanySmtpConfigOut,
    CompanySmtpConfigUpdate,
    CompanySmtpVerifyRequest,
    CompanySmtpVerifyResponse,
    EmailLogOut,
)
from app.services.email.client import EmailService
from app.services.email.schemas import EmailConfig, EmailDeliveryError
from app.services.email.resolver import get_company_kek, get_email_config_for_company

router = APIRouter(prefix="/api/v1/company/smtp", tags=["company-smtp"])


@router.get("", response_model=CompanySmtpConfigOut)
async def get_smtp_config(
    user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    res = await db.execute(
        select(CompanySmtpConfig).where(CompanySmtpConfig.company_id == user.company_id)
    )
    row = res.scalar_one_or_none()
    if not row:
        return CompanySmtpConfigOut(configured=False)
    return CompanySmtpConfigOut(
        configured=True,
        host=row.host,
        port=row.port,
        user=row.user,
        from_email=row.from_email,
        from_name=row.from_name,
        use_tls=row.use_tls,
        use_ssl=row.use_ssl,
        is_active=row.is_active,
        has_password=bool(row.encrypted_password),
        last_tested_at=row.last_tested_at,
    )


@router.put("", response_model=CompanySmtpConfigOut)
async def update_smtp_config(
    body: CompanySmtpConfigUpdate,
    user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    res = await db.execute(
        select(CompanySmtpConfig).where(CompanySmtpConfig.company_id == user.company_id)
    )
    row = res.scalar_one_or_none()
    kek = await get_company_kek(db, user.company_id)

    if not row:
        if not body.password:
            raise HTTPException(status_code=400, detail="Password is required for new SMTP configuration.")
        ciphertext, nonce = encrypt_smtp_password(body.password, kek)
        row = CompanySmtpConfig(
            company_id=user.company_id,
            host=body.host,
            port=body.port,
            user=body.user,
            encrypted_password=ciphertext,
            password_nonce=nonce,
            use_tls=body.use_tls,
            use_ssl=body.use_ssl,
            from_email=str(body.from_email),
            from_name=body.from_name,
            is_active=body.is_active,
        )
        db.add(row)
    else:
        row.host = body.host
        row.port = body.port
        row.user = body.user
        row.from_email = str(body.from_email)
        row.from_name = body.from_name
        row.use_tls = body.use_tls
        row.use_ssl = body.use_ssl
        row.is_active = body.is_active
        if body.password:
            ciphertext, nonce = encrypt_smtp_password(body.password, kek)
            row.encrypted_password = ciphertext
            row.password_nonce = nonce

    db.add(
        ActivityLog(
            company_id=user.company_id,
            actor_type=ActorType.company_user,
            actor_id=user.id,
            action="company.smtp_updated",
            entity_type="company_smtp_config",
            entity_id=user.company_id,
        )
    )
    await db.commit()
    await db.refresh(row)
    return CompanySmtpConfigOut(
        configured=True,
        host=row.host,
        port=row.port,
        user=row.user,
        from_email=row.from_email,
        from_name=row.from_name,
        use_tls=row.use_tls,
        use_ssl=row.use_ssl,
        is_active=row.is_active,
        has_password=True,
        last_tested_at=row.last_tested_at,
    )


@router.post("/verify", response_model=CompanySmtpVerifyResponse)
async def verify_smtp_config(
    body: CompanySmtpVerifyRequest,
    user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    saved_row = (
        await db.execute(
            select(CompanySmtpConfig).where(CompanySmtpConfig.company_id == user.company_id)
        )
    ).scalar_one_or_none()

    tested_saved_config = False

    if body.host and body.user and body.password:
        config = EmailConfig(
            host=body.host,
            port=body.port or 587,
            user=body.user,
            password=body.password,
            use_tls=body.use_tls if body.use_tls is not None else True,
            use_ssl=body.use_ssl if body.use_ssl is not None else False,
            from_email=str(body.from_email or body.user),
            from_name=body.from_name or "Test",
        )
        if (
            saved_row
            and saved_row.host == body.host
            and saved_row.port == (body.port or 587)
            and saved_row.user == body.user
        ):
            tested_saved_config = True
    elif body.host:
        # Caller specified a host but omitted credentials
        if (
            saved_row
            and saved_row.host == body.host
            and (not body.user or saved_row.user == body.user)
        ):
            config = await get_email_config_for_company(db, user.company_id)
            if not config:
                raise HTTPException(
                    status_code=400,
                    detail="No SMTP configuration found to verify. Please provide credentials.",
                )
            tested_saved_config = True
        else:
            raise HTTPException(
                status_code=400,
                detail="Password is required when verifying a new SMTP host.",
            )
    else:
        config = await get_email_config_for_company(db, user.company_id)
        if not config:
            raise HTTPException(
                status_code=400,
                detail="No SMTP configuration found to verify. Please provide credentials.",
            )
        tested_saved_config = True

    service = EmailService(config=config)
    try:
        # Run synchronous SMTP handshake in a thread to avoid blocking the event loop
        res = await asyncio.to_thread(service.verify_connection)
        # Only update last_tested_at on saved row if the tested config was the saved config
        if saved_row and tested_saved_config:
            saved_row.last_tested_at = datetime.now(timezone.utc)
            await db.commit()

        return CompanySmtpVerifyResponse(
            success=True,
            host=res["host"],
            port=res["port"],
            user=res["user"],
            latency_ms=res["latency_ms"],
            message=f"Successfully connected and authenticated with {res['host']}:{res['port']}",
        )
    except EmailDeliveryError as e:
        logger.warning("SMTP verify failed for company %s: %s", user.company_id, e)
        raise HTTPException(
            status_code=400,
            detail="Could not connect to that mail server. Check the host, port and credentials.",
        )


@router.delete("", response_model=CompanySmtpConfigOut)
async def delete_smtp_config(
    user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    res = await db.execute(
        select(CompanySmtpConfig).where(CompanySmtpConfig.company_id == user.company_id)
    )
    row = res.scalar_one_or_none()
    if row:
        await db.delete(row)
        db.add(
            ActivityLog(
                company_id=user.company_id,
                actor_type=ActorType.company_user,
                actor_id=user.id,
                action="company.smtp_deleted",
                entity_type="company_smtp_config",
                entity_id=user.company_id,
            )
        )
        await db.commit()
    return CompanySmtpConfigOut(configured=False)


@router.get("/logs", response_model=List[EmailLogOut])
async def list_email_logs(
    user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    res = await db.execute(
        select(EmailLog)
        .where(EmailLog.company_id == user.company_id)
        .order_by(desc(EmailLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    logs = res.scalars().all()
    return [
        EmailLogOut(
            id=str(log.id),
            sender_email=log.sender_email,
            sender_name=log.sender_name,
            recipient_email=log.recipient_email,
            subject=log.subject,
            template_name=log.template_name,
            status=log.status,
            message_id=log.message_id,
            error_message=log.error_message,
            duration_ms=log.duration_ms,
            source=log.source,
            created_at=log.created_at,
        )
        for log in logs
    ]
