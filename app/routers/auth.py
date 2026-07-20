import uuid
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_company_user,
    get_current_auditor,
)
from app.config import get_settings
from app.database import get_db
from app.encryption import generate_company_kek
from app.services import account_admin
from app.rate_limit import enforce_rate_limit
from app.models.company import Company, CompanyKey, CompanyUser, UserRole
from app.models.auditor import Auditor
from app.models.activity_log import ActivityLog, ActorType
from app.schemas.auth import (
    CompanyInitRequest,
    CompanyInitResponse,
    ReissueKeyResponse,
    ActivationRequest,
    CompanyOut,
    CompanyUserOut,
    CompanyListItem,
    CompanyDeleteRequest,
    AuditorRegister,
    AuditorOut,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Activation key is valid for 48 hours after it is minted.
ACTIVATION_TTL = timedelta(hours=48)
PENDING_PASSWORD = "__pending__"


def _require_internal_key(x_internal_api_key: str) -> None:
    """Guard for operator-only endpoints."""
    settings = get_settings()
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )


def _mint_activation_key(company: Company) -> str:
    """Generate a fresh one-shot activation key, store its hash + expiry on the
    company, and return the plaintext (shown to the operator exactly once)."""
    plaintext = secrets.token_urlsafe(24)
    company.activation_key_hash = hash_password(plaintext)
    company.activation_expires_at = datetime.now(timezone.utc) + ACTIVATION_TTL
    company.activation_used_at = None
    return plaintext


@router.post(
    "/companies",
    response_model=CompanyInitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initialize_company(
    body: CompanyInitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_internal_api_key: Annotated[str, Header()],
):
    """Initialize a company shell + pending admin. Internal only.

    Creates the Company, its per-company KEK, and a pending admin CompanyUser
    (no password yet). Returns a one-shot activation key valid for 48h that the
    admin uses to set their own password. The plaintext key is returned once.
    """
    _require_internal_key(x_internal_api_key)

    # Check email uniqueness (emails are globally unique across all companies)
    existing = await db.execute(
        select(CompanyUser).where(
            func.lower(CompanyUser.email) == body.admin_email.strip().lower()
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create company + mint activation key
    company = Company(name=body.name)
    activation_key = _mint_activation_key(company)
    db.add(company)
    await db.flush()

    # Generate per-company KEK
    _, encrypted_kek, nonce = generate_company_kek()
    company_key = CompanyKey(
        company_id=company.id,
        encrypted_kek=encrypted_kek,
        kek_nonce=nonce,
    )
    db.add(company_key)

    # Create pending admin user (password set later via activation)
    user = CompanyUser(
        company_id=company.id,
        email=body.admin_email.strip().lower(),
        hashed_password=PENDING_PASSWORD,
        role=UserRole.admin,
        is_active=False,
    )
    db.add(user)
    await db.flush()

    # Activity log
    log = ActivityLog(
        company_id=company.id,
        actor_type=ActorType.internal,
        actor_id=user.id,
        action="company.created",
        entity_type="company",
        entity_id=company.id,
    )
    db.add(log)

    # Persist and reload so server-default columns (e.g. accessible_modules,
    # role, is_active) are populated before response validation — otherwise
    # Pydantic accesses unloaded attributes and triggers an illegal lazy load.
    await db.commit()
    await db.refresh(company)
    await db.refresh(user)

    return CompanyInitResponse(
        company=CompanyOut.model_validate(company),
        admin=CompanyUserOut.model_validate(user),
        activation_key=activation_key,
        activation_expires_at=company.activation_expires_at,
    )


@router.post(
    "/companies/{company_id}/reissue-key",
    response_model=ReissueKeyResponse,
)
async def reissue_activation_key(
    company_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_internal_api_key: Annotated[str, Header()],
):
    """Mint a fresh activation key + 48h window for a company whose admin has
    not activated yet. Internal only. No tenant data is touched."""
    _require_internal_key(x_internal_api_key)

    company = (
        await db.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    admin = (
        await db.execute(
            select(CompanyUser).where(
                CompanyUser.company_id == company_id,
                CompanyUser.role == UserRole.admin,
            )
        )
    ).scalars().first()
    if admin is not None and admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin already activated; cannot reissue key",
        )

    activation_key = _mint_activation_key(company)
    await db.commit()
    await db.refresh(company)

    return ReissueKeyResponse(
        activation_key=activation_key,
        activation_expires_at=company.activation_expires_at,
    )


@router.post("/company/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate_company_admin(
    request: Request,
    body: ActivationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Admin claims their pending account: email + one-shot key -> set password.

    On success the password is set, the account is activated, and the key is
    invalidated. No session is issued — the admin logs in normally afterwards.
    All failure modes return the same generic error (no enumeration).
    """
    settings = get_settings()
    await enforce_rate_limit(
        request,
        "activate",
        body.email,
        limit=settings.ACTIVATE_RATE_LIMIT,
        window_seconds=settings.ACTIVATE_RATE_WINDOW,
    )
    generic_error = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired activation details",
    )

    user = (
        await db.execute(
            select(CompanyUser).where(
                func.lower(CompanyUser.email) == body.email.strip().lower()
            )
        )
    ).scalar_one_or_none()

    # Must be a pending admin awaiting activation.
    if user is None or user.is_active or user.hashed_password != PENDING_PASSWORD:
        raise generic_error

    company = (
        await db.execute(select(Company).where(Company.id == user.company_id))
    ).scalar_one_or_none()
    if company is None or not company.activation_key_hash:
        raise generic_error

    # Expiry check.
    expires = company.activation_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is None or expires < datetime.now(timezone.utc):
        raise generic_error

    # Key check (constant-time via bcrypt).
    if not verify_password(body.activation_key, company.activation_key_hash):
        raise generic_error

    # Activate: set real password, flip active, one-shot the key.
    user.hashed_password = hash_password(body.password)
    user.full_name = body.full_name
    user.is_active = True
    company.activation_used_at = datetime.now(timezone.utc)
    company.activation_key_hash = None
    company.activation_expires_at = None

    db.add(
        ActivityLog(
            company_id=company.id,
            actor_type=ActorType.company_user,
            actor_id=user.id,
            action="company.admin_activated",
            entity_type="company_user",
            entity_id=user.id,
        )
    )
    await db.commit()
    return None


@router.get("/companies", response_model=list[CompanyListItem])
async def list_companies(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_internal_api_key: Annotated[str, Header()],
):
    """List all companies with onboarding/activation status. Internal only."""
    _require_internal_key(x_internal_api_key)

    companies = (
        await db.execute(select(Company).order_by(Company.created_at.desc()))
    ).scalars().all()

    now = datetime.now(timezone.utc)
    items: list[CompanyListItem] = []
    for company in companies:
        admin = next(
            (u for u in company.users if u.role == UserRole.admin), None
        )
        expires = company.activation_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        pending = bool(
            company.activation_key_hash
            and expires is not None
            and expires > now
        )
        items.append(
            CompanyListItem(
                id=company.id,
                name=company.name,
                admin_email=admin.email if admin else None,
                admin_active=bool(admin and admin.is_active),
                profile_completed=company.profile_completed,
                activation_pending=pending,
                activation_expires_at=company.activation_expires_at,
                created_at=company.created_at,
                archived=company.archived_at is not None,
            )
        )
    return items


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: uuid.UUID,
    body: CompanyDeleteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_internal_api_key: Annotated[str, Header()],
):
    """Archive a company. Internal only.

    Encrypted tenant data cannot be meaningfully deleted, so instead of a hard
    cascade we archive: every company login is disabled and the company's name +
    admin email are freed so a fresh company can reuse them. The on-disk encrypted
    files are retained. Requires ``confirm_name`` to match the company name.
    """
    _require_internal_key(x_internal_api_key)

    company = (
        await db.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    if body.confirm_name != company.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm_name does not match the company name",
        )

    try:
        await account_admin.archive_company(db, company)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    await db.commit()
    return None


@router.post("/company/login", response_model=TokenResponse)
async def company_login(
    request: Request,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Login for company users."""
    settings = get_settings()
    await enforce_rate_limit(
        request,
        "login",
        body.email,
        limit=settings.LOGIN_RATE_LIMIT,
        window_seconds=settings.LOGIN_RATE_WINDOW,
    )
    result = await db.execute(
        select(CompanyUser).where(CompanyUser.email == body.email)
    )
    user = result.scalar_one_or_none()
    # Reject unknown users, wrong passwords, and pending/deactivated accounts
    # (a pending admin still has the "__pending__" placeholder, which never
    # verifies) — all with the same generic error.
    if (
        user is None
        or not user.is_active
        or not verify_password(body.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    # Defense-in-depth: block login into an archived company even if a user row
    # were somehow still active (archiving deactivates all users, but this makes
    # the company-level state authoritative).
    company = (
        await db.execute(select(Company).where(Company.id == user.company_id))
    ).scalar_one_or_none()
    if company is None or company.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return TokenResponse(
        access_token=create_access_token(user.id, "company_user"),
        refresh_token=create_refresh_token(user.id, "company_user"),
        role=user.role,
        full_name=user.full_name,
    )


@router.post("/company/refresh", response_model=TokenResponse)
async def company_refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Refresh access token for company users."""
    payload = decode_token(body.refresh_token)
    if payload.get("principal_type") != "company_user" or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(CompanyUser).where(CompanyUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return TokenResponse(
        access_token=create_access_token(user.id, "company_user"),
        refresh_token=create_refresh_token(user.id, "company_user"),
        role=user.role,
        full_name=user.full_name,
    )


@router.get("/company/me", response_model=CompanyUserOut)
async def company_me(
    user: Annotated[CompanyUser, Depends(get_current_company_user)],
):
    """Get current company user profile."""
    return CompanyUserOut.model_validate(user)


# === Auditor auth ===


@router.post(
    "/auditor/register",
    response_model=AuditorOut,
    status_code=status.HTTP_201_CREATED,
)
async def auditor_register(
    body: AuditorRegister,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Open self-registration for auditors."""
    existing = await db.execute(
        select(Auditor).where(Auditor.email == body.email)
    )
    auditor_obj = existing.scalar_one_or_none()
    
    if auditor_obj:
        if auditor_obj.hashed_password == "__pending__":
            # Re-use the placeholder auditor account created by an invite
            auditor_obj.hashed_password = hash_password(body.password)
            auditor_obj.name = body.name
            await db.commit()
            await db.refresh(auditor_obj)
            return auditor_obj
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
            
    auditor_obj = Auditor(
        email=body.email,
        hashed_password=hash_password(body.password),
        name=body.name,
    )
    db.add(auditor_obj)
    await db.flush()

    # Convert any pending engagement invites addressed to this email into grants.
    from app.models.auditease import PendingAuditorInvite, AuditorEngagementGrant, GrantStatus
    pend_res = await db.execute(
        select(PendingAuditorInvite).where(
            func.lower(PendingAuditorInvite.email) == body.email.strip().lower()
        )
    )
    pendings = pend_res.scalars().all()
    for pend in pendings:
        db.add(AuditorEngagementGrant(
            auditor_id=auditor_obj.id,
            engagement_id=pend.engagement_id,
            status=GrantStatus.invited,
        ))
        await db.delete(pend)

    await db.commit()
    await db.refresh(auditor_obj)
    return AuditorOut.model_validate(auditor_obj)


@router.post("/auditor/login", response_model=TokenResponse)
async def auditor_login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Login for auditors."""
    result = await db.execute(
        select(Auditor).where(Auditor.email == body.email)
    )
    auditor = result.scalar_one_or_none()
    if auditor is None or not verify_password(body.password, auditor.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return TokenResponse(
        access_token=create_access_token(auditor.id, "auditor"),
        refresh_token=create_refresh_token(auditor.id, "auditor"),
    )


@router.post("/auditor/refresh", response_model=TokenResponse)
async def auditor_refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Refresh access token for auditors."""
    payload = decode_token(body.refresh_token)
    if payload.get("principal_type") != "auditor" or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    auditor_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(Auditor).where(Auditor.id == auditor_id))
    auditor = result.scalar_one_or_none()
    if auditor is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auditor not found",
        )
    return TokenResponse(
        access_token=create_access_token(auditor.id, "auditor"),
        refresh_token=create_refresh_token(auditor.id, "auditor"),
    )


@router.get("/auditor/me", response_model=AuditorOut)
async def auditor_me(
    auditor: Annotated[Auditor, Depends(get_current_auditor)],
):
    """Get current auditor profile."""
    return AuditorOut.model_validate(auditor)
