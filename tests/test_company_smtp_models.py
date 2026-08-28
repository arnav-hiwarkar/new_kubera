import uuid
import pytest
from sqlalchemy import select
from app.models.company import Company
from app.models.company_smtp import CompanySmtpConfig, EmailLog


@pytest.mark.asyncio
async def test_company_smtp_config_model_crud(db):
    company = Company(name="Acme Corp")
    db.add(company)
    await db.flush()

    config = CompanySmtpConfig(
        company_id=company.id,
        host="smtp.office365.com",
        port=587,
        user="audit@acme.com",
        encrypted_password=b"encrypted_secret",
        password_nonce=b"nonce_12byte_",
        use_tls=True,
        use_ssl=False,
        from_email="audit@acme.com",
        from_name="Acme Audit",
    )
    db.add(config)
    await db.commit()

    res = await db.execute(
        select(CompanySmtpConfig).where(CompanySmtpConfig.company_id == company.id)
    )
    saved = res.scalar_one_or_none()
    assert saved is not None
    assert saved.host == "smtp.office365.com"
    assert saved.port == 587
    assert saved.from_email == "audit@acme.com"
    assert saved.is_active is True


@pytest.mark.asyncio
async def test_email_log_model(db):
    company = Company(name="Acme Corp")
    db.add(company)
    await db.flush()

    log_entry = EmailLog(
        company_id=company.id,
        sender_email="audit@acme.com",
        sender_name="Acme Audit",
        recipient_email="auditor@firm.com",
        subject="Audit Invitation",
        template_name="auditor_invite.html",
        status="sent",
        message_id="<msg123@acme.com>",
        duration_ms=142.5,
        source="auditease.invite",
    )
    db.add(log_entry)
    await db.commit()

    res = await db.execute(
        select(EmailLog).where(EmailLog.company_id == company.id)
    )
    saved = res.scalar_one_or_none()
    assert saved is not None
    assert saved.recipient_email == "auditor@firm.com"
    assert saved.status == "sent"
