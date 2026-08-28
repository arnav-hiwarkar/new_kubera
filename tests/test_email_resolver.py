import pytest
from app.encryption import generate_company_kek, encrypt_smtp_password, decrypt_smtp_password
from app.models.company import Company, CompanyKey
from app.models.company_smtp import CompanySmtpConfig
from app.services.email.resolver import (
    get_email_config_for_company,
    get_email_service_for_company,
    record_email_log,
)


def test_smtp_password_encryption_roundtrip():
    raw_kek, _, _ = generate_company_kek()
    password = "SuperSecretPassword123!"
    ciphertext, nonce = encrypt_smtp_password(password, raw_kek)
    decrypted = decrypt_smtp_password(ciphertext, nonce, raw_kek)
    assert decrypted == password


def test_smtp_password_tamper_fails():
    raw_kek, _, _ = generate_company_kek()
    ciphertext, nonce = encrypt_smtp_password("password", raw_kek)
    # Corrupt ciphertext
    corrupted = bytearray(ciphertext)
    corrupted[0] ^= 0xFF
    with pytest.raises(Exception):
        decrypt_smtp_password(bytes(corrupted), nonce, raw_kek)


@pytest.mark.asyncio
async def test_resolver_fallback_to_default(db):
    company = Company(name="No SMTP Company")
    db.add(company)
    await db.flush()

    config = await get_email_config_for_company(db, company.id)
    assert config is None

    service = await get_email_service_for_company(db, company.id)
    assert service.config.from_email == "kubera@ethdc.in"


@pytest.mark.asyncio
async def test_resolver_with_custom_company_smtp(db):
    raw_kek, encrypted_kek, nonce_kek = generate_company_kek()
    company = Company(name="Custom SMTP Co")
    db.add(company)
    await db.flush()

    ckey = CompanyKey(
        company_id=company.id,
        encrypted_kek=encrypted_kek,
        kek_nonce=nonce_kek,
    )
    db.add(ckey)

    pw_cipher, pw_nonce = encrypt_smtp_password("OfficePass999", raw_kek)
    smtp_cfg = CompanySmtpConfig(
        company_id=company.id,
        host="smtp.office365.com",
        port=587,
        user="audit@custom.com",
        encrypted_password=pw_cipher,
        password_nonce=pw_nonce,
        use_tls=True,
        use_ssl=False,
        from_email="audit@custom.com",
        from_name="Custom Compliance",
        is_active=True,
    )
    db.add(smtp_cfg)
    await db.commit()

    config = await get_email_config_for_company(db, company.id)
    assert config is not None
    assert config.host == "smtp.office365.com"
    assert config.port == 587
    assert config.user == "audit@custom.com"
    assert config.password == "OfficePass999"
    assert config.from_email == "audit@custom.com"
    assert config.from_name == "Custom Compliance"

    service = await get_email_service_for_company(db, company.id)
    assert service.config.host == "smtp.office365.com"
    assert service.config.password == "OfficePass999"


@pytest.mark.asyncio
async def test_record_email_log(db):
    company = Company(name="Log Test Co")
    db.add(company)
    await db.flush()

    log_entry = await record_email_log(
        db=db,
        company_id=company.id,
        sender_email="audit@custom.com",
        sender_name="Custom Audit",
        recipient_email="auditor@firm.com",
        subject="Audit Plan FY25",
        template_name="auditor_invite.html",
        status="sent",
        source="auditease.invite",
        message_id="<test@custom.com>",
        duration_ms=120.5,
    )
    assert log_entry.id is not None
    assert log_entry.status == "sent"
    assert log_entry.duration_ms == 120.5
