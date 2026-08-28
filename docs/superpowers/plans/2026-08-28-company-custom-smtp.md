# Company Custom SMTP, Auditor Invite Emailing & Audit Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow companies to configure their own custom SMTP email server in Company Profile with AES-256-GCM envelope encryption, live-test connection verification, automated fallback to central `kubera@ethdc.in`, asynchronous auditor onboarding invitation emails, and full sent-email audit logging.

**Architecture:** 
1. Database layer with `company_smtp_configs` (encrypted passwords via tenant KEK) and `email_logs`.
2. Core resolver service in `app/services/email/resolver.py` providing dynamic transport resolution and email audit tracking.
3. Secure REST API endpoints under `/api/v1/company/smtp` with strict RBAC (admin only) and anti-IDOR tenant isolation.
4. Auditor invite workflow dispatching branded onboarding emails with smart routing (`/auditor/register` vs `/auditor/login`).
5. Frontend settings card `CompanySmtpCard.tsx` with live "Test Connection", "Save", and "Reset to Default" actions.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (asyncio), Alembic, Pydantic v2, AES-256-GCM (cryptography), Jinja2, Celery 5.5, Redis, React, TypeScript, Tailwind CSS, pytest, vitest.

## Global Constraints
- `smtp_password` must always be encrypted at rest using AES-256-GCM under the tenant's `CompanyKey` KEK.
- `GET` API endpoints must never expose passwords, decrypted text, or KEKs (`has_password: bool` only).
- When custom SMTP is unconfigured or deleted, email delivery must automatically fall back to `kubera@ethdc.in`.
- SMTP connection downtime must never roll back or abort database audit grants during auditor invitation.
- Non-admin users and cross-tenant access must be strictly rejected with `403 Forbidden`.

---

### Task 1: Database Models & Alembic Migration

**Files:**
- Create: `app/models/company_smtp.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/company.py`
- Create: `alembic/versions/f9a8b7c6d5e4_add_company_smtp_and_email_logs.py`
- Test: `tests/test_company_smtp_models.py`

**Interfaces:**
- Consumes: SQLAlchemy `Base`, `TimestampMixin`, `Company`.
- Produces: `CompanySmtpConfig` and `EmailLog` database models.

- [ ] **Step 1: Write failing tests for CompanySmtpConfig and EmailLog models**

```python
# tests/test_company_smtp_models.py
import uuid
import pytest
from sqlalchemy import select
from app.models.company import Company
from app.models.company_smtp import CompanySmtpConfig, EmailLog


@pytest.mark.asyncio
async def test_company_smtp_config_model_crud(db_session):
    company = Company(name="Acme Corp")
    db_session.add(company)
    await db_session.flush()

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
    db_session.add(config)
    await db_session.commit()

    res = await db_session.execute(
        select(CompanySmtpConfig).where(CompanySmtpConfig.company_id == company.id)
    )
    saved = res.scalar_one_or_none()
    assert saved is not None
    assert saved.host == "smtp.office365.com"
    assert saved.port == 587
    assert saved.from_email == "audit@acme.com"
    assert saved.is_active is True


@pytest.mark.asyncio
async def test_email_log_model(db_session):
    company = Company(name="Acme Corp")
    db_session.add(company)
    await db_session.flush()

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
    db_session.add(log_entry)
    await db_session.commit()

    res = await db_session.execute(
        select(EmailLog).where(EmailLog.company_id == company.id)
    )
    saved = res.scalar_one_or_none()
    assert saved is not None
    assert saved.recipient_email == "auditor@firm.com"
    assert saved.status == "sent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_company_smtp_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.company_smtp'`

- [ ] **Step 3: Implement `app/models/company_smtp.py` and Alembic migration**

`app/models/company_smtp.py`:
```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Float, Text, LargeBinary, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class CompanySmtpConfig(Base, TimestampMixin):
    __tablename__ = "company_smtp_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    user: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_password: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    password_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    from_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company = relationship("Company", back_populates="smtp_config")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="sent")
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
```

In `app/models/company.py`, add the relationship:
```python
smtp_config = relationship("CompanySmtpConfig", back_populates="company", uselist=False, cascade="all, delete-orphan")
```

In `app/models/__init__.py`, import `CompanySmtpConfig` and `EmailLog`.

Generate and apply the Alembic migration:
`uv run alembic revision --autogenerate -m "add company smtp configs and email logs"`
`uv run alembic upgrade head`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_company_smtp_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models alembic/versions tests/test_company_smtp_models.py
git commit -m "feat(email): add CompanySmtpConfig and EmailLog models and migration"
```

---

### Task 2: Password Encryption & Company Email Resolver Service

**Files:**
- Modify: `app/encryption.py`
- Create: `app/services/email/resolver.py`
- Modify: `app/services/email/__init__.py`
- Test: `tests/test_email_resolver.py`

**Interfaces:**
- Consumes: `CompanySmtpConfig`, `CompanyKey`, `EmailService`, `EmailConfig`, `app.encryption`.
- Produces:
  - `encrypt_smtp_password(password: str, company_kek: bytes) -> tuple[bytes, bytes]`
  - `decrypt_smtp_password(encrypted_pw: bytes, nonce: bytes, company_kek: bytes) -> str`
  - `get_email_config_for_company(db: AsyncSession, company_id: uuid.UUID) -> Optional[EmailConfig]`
  - `get_email_service_for_company(db: AsyncSession, company_id: uuid.UUID) -> EmailService`
  - `record_email_log(db: AsyncSession, ...)`

- [ ] **Step 1: Write failing tests for resolver and password encryption**

```python
# tests/test_email_resolver.py
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
async def test_resolver_fallback_to_default(db_session):
    company = Company(name="No SMTP Company")
    db_session.add(company)
    await db_session.flush()

    config = await get_email_config_for_company(db_session, company.id)
    assert config is None

    service = await get_email_service_for_company(db_session, company.id)
    assert service.config.from_email == "kubera@ethdc.in"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_email_resolver.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement encryption helpers and `app/services/email/resolver.py`**

In `app/encryption.py`:
```python
def encrypt_smtp_password(password: str, company_kek: bytes) -> tuple[bytes, bytes]:
    """Encrypt an SMTP password string with AES-GCM under the company KEK."""
    aesgcm = AESGCM(company_kek)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, password.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_smtp_password(ciphertext: bytes, nonce: bytes, company_kek: bytes) -> str:
    """Decrypt an AES-GCM encrypted SMTP password using the company KEK."""
    aesgcm = AESGCM(company_kek)
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_bytes.decode("utf-8")
```

`app/services/email/resolver.py`:
```python
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
    return log_entry
```

Update `app/services/email/__init__.py` with exports.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_email_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/encryption.py app/services/email tests/test_email_resolver.py
git commit -m "feat(email): implement company SMTP resolver and password envelope encryption"
```

---

### Task 3: REST API Endpoints for Company SMTP

**Files:**
- Create: `app/schemas/company_smtp.py`
- Create: `app/routers/company_smtp.py`
- Modify: `app/main.py`
- Test: `tests/test_company_smtp_api.py`

**Interfaces:**
- Consumes: `CompanySmtpConfig`, `CompanyUser`, `require_admin`, `get_current_company_user`, `get_db`.
- Produces: `/api/v1/company/smtp` GET, PUT, POST /verify, DELETE, and GET /logs.

- [ ] **Step 1: Write failing tests for Company SMTP REST API**

```python
# tests/test_company_smtp_api.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_smtp_config_unconfigured(client: AsyncClient, admin_token: str):
    res = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is False


@pytest.mark.asyncio
async def test_save_and_get_smtp_config(client: AsyncClient, admin_token: str):
    payload = {
        "host": "smtp.office365.com",
        "port": 587,
        "user": "audit@acme.com",
        "password": "Password123!",
        "use_tls": True,
        "use_ssl": False,
        "from_email": "audit@acme.com",
        "from_name": "Acme Compliance",
    }
    put_res = await client.put("/api/v1/company/smtp", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["configured"] is True
    assert data["host"] == "smtp.office365.com"
    assert data["has_password"] is True
    assert "password" not in data  # NEVER LEAK PASSWORD!


@pytest.mark.asyncio
async def test_employee_and_auditor_rejected(client: AsyncClient, employee_token: str, auditor_token: str):
    res1 = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {employee_token}"})
    assert res1.status_code == 403

    res2 = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {auditor_token}"})
    assert res2.status_code in (401, 403)


@pytest.mark.asyncio
async def test_delete_smtp_config(client: AsyncClient, admin_token: str):
    del_res = await client.delete("/api/v1/company/smtp", headers={"Authorization": f"Bearer {admin_token}"})
    assert del_res.status_code == 200
    assert del_res.json()["configured"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_company_smtp_api.py -v`
Expected: FAIL with 404

- [ ] **Step 3: Implement schemas, endpoints, and route registration**

`app/schemas/company_smtp.py`:
```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class CompanySmtpConfigOut(BaseModel):
    configured: bool
    host: Optional[str] = None
    port: Optional[int] = 587
    user: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    use_tls: bool = True
    use_ssl: bool = False
    is_active: bool = True
    has_password: bool = False
    last_tested_at: Optional[datetime] = None


class CompanySmtpConfigUpdate(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535, default=587)
    user: str = Field(min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=1)  # Optional if retaining existing
    use_tls: bool = True
    use_ssl: bool = False
    from_email: EmailStr
    from_name: str = Field(min_length=1, max_length=255)
    is_active: bool = True


class CompanySmtpVerifyRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = None


class CompanySmtpVerifyResponse(BaseModel):
    success: bool
    host: str
    port: int
    user: str
    latency_ms: float
    message: str
```

`app/routers/company_smtp.py`:
```python
from datetime import datetime, timezone
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
    else:
        config = await get_email_config_for_company(db, user.company_id)
        if not config:
            raise HTTPException(status_code=400, detail="No SMTP configuration found to verify. Please provide credentials.")

    service = EmailService(config=config)
    try:
        res = service.verify_connection()
        # Update last_tested_at on saved row if exists
        saved_row = (await db.execute(select(CompanySmtpConfig).where(CompanySmtpConfig.company_id == user.company_id))).scalar_one_or_none()
        if saved_row:
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
        raise HTTPException(status_code=400, detail=str(e))


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
```

Register router in `app/main.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_company_smtp_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/company_smtp.py app/routers/company_smtp.py app/main.py tests/test_company_smtp_api.py
git commit -m "feat(api): implement company custom SMTP management and verification endpoints"
```

---

### Task 4: Auditor Invitation Emailing & Celery Background Task

**Files:**
- Create: `app/services/email/templates/auditor_invite.html`
- Modify: `app/services/email/tasks.py`
- Modify: `app/routers/auditease.py:1080-1095`
- Test: `tests/test_auditor_invite_email.py`

**Interfaces:**
- Consumes: `EmailMessage`, `send_email_async`, `get_email_config_for_company`.
- Produces: Automated invite emails with smart `/auditor/register` vs `/auditor/login` buttons.

- [ ] **Step 1: Write failing tests for auditor invite email dispatch**

```python
# tests/test_auditor_invite_email.py
from unittest.mock import patch, MagicMock
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@patch("app.routers.auditease.send_email_async")
async def test_invite_unregistered_auditor_dispatches_register_email(
    mock_send_task, client: AsyncClient, admin_token: str, engagement_id: str
):
    mock_send_task.delay.return_value = MagicMock(id="task-123")
    payload = {"email": "new_auditor@test.com", "area_permissions": None}

    res = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/auditors/invite",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    mock_send_task.delay.assert_called_once()
    call_args = mock_send_task.delay.call_args[0][0]
    assert "new_auditor@test.com" in call_args["to"]
    assert "auditor/register" in call_args["template_context"]["action_button"]["url"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auditor_invite_email.py -v`
Expected: FAIL

- [ ] **Step 3: Implement template and hook up invite dispatch in `app/routers/auditease.py`**

`app/services/email/templates/auditor_invite.html`:
```html
{% extends "base.html" %}

{% block content %}
  <h2 style="margin-top: 0; color: #0f172a; font-size: 18px; font-weight: 600;">
    Audit Portal Invitation
  </h2>
  
  <p style="margin-bottom: 16px; color: #334155;">
    Hello,
  </p>

  <p style="margin-bottom: 16px; color: #334155;">
    <strong>{{ company_name }}</strong> has invited you to audit their financial and compliance records for the engagement period <strong>{{ period_label }}</strong> on Kubera.
  </p>

  <div class="button-container" style="margin: 28px 0;">
    <a href="{{ action_button.url }}" class="button" target="_blank" style="display: inline-block; padding: 12px 24px; background-color: #2563eb; color: #ffffff !important; text-decoration: none; font-weight: 600; border-radius: 6px; font-size: 15px;">
      {{ action_button.label }}
    </a>
  </div>

  <p style="font-size: 13px; color: #64748b; margin-top: 24px;">
    If the button above does not work, copy and paste this link into your browser:<br>
    <a href="{{ action_button.url }}" style="color: #2563eb; word-break: break-all;">{{ action_button.url }}</a>
  </p>
{% endblock %}
```

In `app/routers/auditease.py`, after creating `AuditorEngagementGrant` or `PendingAuditorInvite`:
```python
    # Dispatch invitation email asynchronously in background
    from app.services.email.resolver import get_email_config_for_company, record_email_log
    from app.services.email.tasks import send_email_async
    from app.services.email.schemas import EmailMessage

    domain = get_settings().DOMAIN
    proto = "https" if domain != "localhost" else "http"
    base_url = f"{proto}://{domain}"

    if auditor:
        action_url = f"{base_url}/auditor/login"
        action_label = "Log In to Audit Portal"
    else:
        action_url = f"{base_url}/auditor/register?email={email}"
        action_label = "Set Up Auditor Account"

    company_config = await get_email_config_for_company(db, current_user.company_id)
    company_name = (await db.execute(select(Company.name).where(Company.id == current_user.company_id))).scalar_one()

    email_msg = EmailMessage(
        to=[email],
        subject=f"Audit Invitation: {company_name} - {eng.period_label}",
        template_name="auditor_invite.html",
        template_context={
            "company_name": company_name,
            "period_label": eng.period_label,
            "action_button": {
                "label": action_label,
                "url": action_url,
            },
            "footer_note": f"Sent by {company_name} via Kubera Corporate Compliance.",
        },
    )

    try:
        send_email_async.delay(
            email_msg.model_dump(),
            company_config.model_dump() if company_config else None,
        )
    except Exception as e:
        logger.error(f"Failed to queue auditor invite email: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_auditor_invite_email.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/email/templates/auditor_invite.html app/routers/auditease.py tests/test_auditor_invite_email.py
git commit -m "feat(auditease): dispatch branded invitation email on auditor invite with smart routing"
```

---

### Task 5: Frontend Outbound Email & SMTP Settings Component

**Files:**
- Create: `frontend/src/api/endpoints/companySmtp.ts`
- Create: `frontend/src/api/hooks/companySmtp.ts`
- Create: `frontend/src/pages/company/settings/CompanySmtpCard.tsx`
- Modify: `frontend/src/pages/company/settings/CompanyProfilePage.tsx`
- Test: `frontend/src/pages/company/settings/CompanySmtpCard.test.tsx`

**Interfaces:**
- Consumes: `companyClient`, `useToast`, `Button`, `Input`, `Field`.
- Produces: Interactive SMTP settings card with live verification, save, and reset actions.

- [ ] **Step 1: Write failing frontend unit tests for CompanySmtpCard**

```typescript
// frontend/src/pages/company/settings/CompanySmtpCard.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { CompanySmtpCard } from './CompanySmtpCard'

describe('CompanySmtpCard', () => {
  it('renders status badge and fields', async () => {
    render(<CompanySmtpCard canEdit={true} />)
    expect(screen.getByText(/Outbound Email & Custom SMTP/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/SMTP Host/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test CompanySmtpCard.test.tsx`
Expected: FAIL

- [ ] **Step 3: Implement API endpoints, hooks, and `CompanySmtpCard.tsx`**

`frontend/src/api/endpoints/companySmtp.ts`:
```typescript
import { companyClient } from '@/api/clients/company'

export interface CompanySmtpConfig {
  configured: boolean
  host: string | null
  port: number
  user: string | null
  from_email: string | null
  from_name: string | null
  use_tls: boolean
  use_ssl: boolean
  is_active: boolean
  has_password: boolean
  last_tested_at: string | null
}

export interface CompanySmtpUpdate {
  host: string
  port: number
  user: string
  password?: string
  from_email: string
  from_name: string
  use_tls: boolean
  use_ssl: boolean
  is_active: boolean
}

export interface CompanySmtpVerifyPayload {
  host?: string
  port?: number
  user?: string
  password?: string
  from_email?: string
  from_name?: string
  use_tls?: boolean
  use_ssl?: boolean
}

export const companySmtpApi = {
  get: () => companyClient.get<CompanySmtpConfig>('/api/v1/company/smtp'),
  update: (body: CompanySmtpUpdate) => companyClient.put<CompanySmtpConfig>('/api/v1/company/smtp', { body }),
  verify: (body: CompanySmtpVerifyPayload) => companyClient.post<{ success: boolean; latency_ms: number; message: string }>('/api/v1/company/smtp/verify', { body }),
  reset: () => companyClient.delete<CompanySmtpConfig>('/api/v1/company/smtp'),
}
```

`frontend/src/api/hooks/companySmtp.ts`:
```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { companySmtpApi } from '@/api/endpoints/companySmtp'

export function useCompanySmtp() {
  return useQuery({
    queryKey: ['companySmtp'],
    queryFn: () => companySmtpApi.get(),
  })
}

export function useUpdateCompanySmtp() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: companySmtpApi.update,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['companySmtp'] }),
  })
}

export function useVerifyCompanySmtp() {
  return useMutation({
    mutationFn: companySmtpApi.verify,
  })
}

export function useResetCompanySmtp() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: companySmtpApi.reset,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['companySmtp'] }),
  })
}
```

`frontend/src/pages/company/settings/CompanySmtpCard.tsx`:
Implement card with inputs, status badge, Test Connection button with spinner and result toast, Save button, and Reset button.

Integrate in `frontend/src/pages/company/settings/CompanyProfilePage.tsx`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test CompanySmtpCard.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): add company custom SMTP configuration card with live verification"
```

---

### Task 6: Full Regression Suite Verification & Documentation

**Files:**
- Modify: `README.md`
- Test: Full backend test suite (`uv run pytest tests/`) + frontend test suite (`npm --prefix frontend test`)

- [ ] **Step 1: Run complete backend test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 2: Run frontend test suite**

Run: `npm --prefix frontend test`
Expected: All tests PASS.

- [ ] **Step 3: Update `README.md`**

Add Company Custom SMTP & Auditor Onboarding section to `README.md`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add company custom SMTP and auditor invite documentation"
```
