import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy import select, func
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
from app.models.company import Company, CompanyKey, CompanyUser
from app.models.auditor import Auditor
from app.models.activity_log import ActivityLog, ActorType
from app.schemas.auth import (
    CompanyCreateRequest,
    CompanyUserCreate,
    CompanyOut,
    CompanyUserOut,
    CompanyWithAdmin,
    AuditorRegister,
    AuditorOut,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/companies",
    response_model=CompanyWithAdmin,
    status_code=status.HTTP_201_CREATED,
)
async def create_company(
    body: CompanyCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_internal_api_key: Annotated[str, Header()],
):
    """Create a new company with its first admin user. Internal only."""
    settings = get_settings()
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )

    # Check email uniqueness
    existing = await db.execute(
        select(CompanyUser).where(CompanyUser.email == body.admin.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create company
    company = Company(name=body.name)
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

    # Create admin user
    user = CompanyUser(
        company_id=company.id,
        email=body.admin.email,
        hashed_password=hash_password(body.admin.password),
        full_name=body.admin.email.split("@")[0],
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

    return CompanyWithAdmin(
        company=CompanyOut.model_validate(company),
        admin=CompanyUserOut.model_validate(user),
    )


@router.post("/company/login", response_model=TokenResponse)
async def company_login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Login for company users."""
    result = await db.execute(
        select(CompanyUser).where(CompanyUser.email == body.email)
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
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
<<<<<<< HEAD
    db.add(auditor_obj)
    await db.commit()
    await db.refresh(auditor_obj)
    return AuditorOut.model_validate(auditor_obj)
=======
    db.add(auditor)
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
            auditor_id=auditor.id,
            engagement_id=pend.engagement_id,
            status=GrantStatus.invited,
        ))
        await db.delete(pend)

    return AuditorOut.model_validate(auditor)
>>>>>>> new_frontend


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
