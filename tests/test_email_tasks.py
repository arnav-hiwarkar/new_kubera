from unittest.mock import patch
import pytest
from sqlalchemy import select

from app.encryption import generate_company_kek, encrypt_smtp_password
from app.models.company import Company, CompanyKey
from app.models.company_smtp import CompanySmtpConfig, EmailLog
from app.services.email.schemas import EmailDeliveryResult, EmailDeliveryError
from app.services.email.tasks import send_email_async


@pytest.mark.asyncio
async def test_send_email_async_updates_log_on_success(db):
    company = Company(name="Task Success Co")
    db.add(company)
    await db.flush()

    log_entry = EmailLog(
        company_id=company.id,
        sender_email="kubera@ethdc.in",
        sender_name="Kubera Compliance",
        recipient_email="auditor@test.com",
        subject="Audit Invite",
        template_name="auditor_invite.html",
        status="queued",
        source="auditease.invite",
    )
    db.add(log_entry)
    await db.commit()

    message_dict = {
        "to": ["auditor@test.com"],
        "subject": "Audit Invite",
        "body_text": "Hello Auditor",
    }

    mock_result = EmailDeliveryResult(
        success=True,
        message_id="<msg-abc-123@ethdc.in>",
        recipients=["auditor@test.com"],
        duration_ms=45.2,
    )

    with patch("app.services.email.tasks.EmailService.send", return_value=mock_result):
        res = send_email_async(
            message_dict=message_dict,
            company_id=str(company.id),
            log_id=str(log_entry.id),
        )

    assert res["success"] is True
    assert res["message_id"] == "<msg-abc-123@ethdc.in>"

    # Verify EmailLog was updated in DB
    await db.refresh(log_entry)
    assert log_entry.status == "sent"
    assert log_entry.message_id == "<msg-abc-123@ethdc.in>"
    assert log_entry.duration_ms == 45.2


@pytest.mark.asyncio
async def test_send_email_async_updates_log_on_permanent_error(db):
    company = Company(name="Task Failure Co")
    db.add(company)
    await db.flush()

    log_entry = EmailLog(
        company_id=company.id,
        sender_email="kubera@ethdc.in",
        sender_name="Kubera Compliance",
        recipient_email="auditor@test.com",
        subject="Audit Invite",
        template_name="auditor_invite.html",
        status="queued",
        source="auditease.invite",
    )
    db.add(log_entry)
    await db.commit()

    message_dict = {
        "to": ["auditor@test.com"],
        "subject": "Audit Invite",
        "body_text": "Hello Auditor",
    }

    with patch("app.services.email.tasks.EmailService.send", side_effect=EmailDeliveryError("SMTP_HOST is not configured.")):
        res = send_email_async(
            message_dict=message_dict,
            company_id=str(company.id),
            log_id=str(log_entry.id),
        )

    assert res["success"] is False
    assert "not configured" in res["error"]

    # Verify EmailLog was updated to failed
    await db.refresh(log_entry)
    assert log_entry.status == "failed"
    assert "SMTP_HOST is not configured" in log_entry.error_message


@pytest.mark.asyncio
async def test_send_email_async_resolves_company_credentials_in_worker(db):
    raw_kek, encrypted_kek, nonce_kek = generate_company_kek()
    company = Company(name="Worker Decrypt Co")
    db.add(company)
    await db.flush()

    ckey = CompanyKey(
        company_id=company.id,
        encrypted_kek=encrypted_kek,
        kek_nonce=nonce_kek,
    )
    db.add(ckey)

    pw_cipher, pw_nonce = encrypt_smtp_password("WorkerDecryptedSecret!", raw_kek)
    smtp_cfg = CompanySmtpConfig(
        company_id=company.id,
        host="smtp.customcorp.com",
        port=587,
        user="mailer@customcorp.com",
        encrypted_password=pw_cipher,
        password_nonce=pw_nonce,
        use_tls=True,
        use_ssl=False,
        from_email="mailer@customcorp.com",
        from_name="Custom Corp Mailer",
        is_active=True,
    )
    db.add(smtp_cfg)
    await db.commit()

    message_dict = {
        "to": ["partner@firm.com"],
        "subject": "Verification Request",
        "body_text": "Please verify documents",
    }

    captured_config = None

    def fake_send(self, msg):
        nonlocal captured_config
        captured_config = self.config
        return EmailDeliveryResult(
            success=True,
            message_id="<worker-test@customcorp.com>",
            recipients=msg.to,
            duration_ms=25.0,
        )

    with patch("app.services.email.tasks.EmailService.send", side_effect=fake_send, autospec=True):
        res = send_email_async(
            message_dict=message_dict,
            company_id=str(company.id),
        )

    assert res["success"] is True
    assert captured_config is not None
    assert captured_config.host == "smtp.customcorp.com"
    assert captured_config.user == "mailer@customcorp.com"
    assert captured_config.password == "WorkerDecryptedSecret!"
    assert captured_config.from_email == "mailer@customcorp.com"
