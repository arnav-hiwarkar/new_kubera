import uuid
import secrets
from typing import Annotated, Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.lead import Lead, LeadStatus
from app.models.company import Company, CompanyKey, CompanyUser, UserRole
from app.schemas.lead import (
    LeadInterestRequest,
    LeadInterestResponse,
    LeadOut,
    LeadStatusUpdate,
    LeadProvisionResponse,
)
from app.rate_limit import enforce_rate_limit
from app.auth import hash_password
from app.encryption import generate_company_kek
from app.routers.auth import _mint_activation_key, PENDING_PASSWORD

router = APIRouter(tags=["leads"])


def _require_internal_key(x_internal_api_key: str) -> None:
    """Guard for owner/internal endpoints using constant-time comparison."""
    settings = get_settings()
    if not x_internal_api_key or not secrets.compare_digest(
        x_internal_api_key, settings.INTERNAL_API_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal API key",
        )


@router.post(
    "/api/v1/leads/interest",
    response_model=LeadInterestResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_lead_interest(
    request: Request,
    body: LeadInterestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Public lead capture endpoint with rate limiting, honeypot trap, and anti-enumeration."""
    # 1. Anti-bot honeypot check: If the hidden honeypot field is filled, silently succeed without DB write.
    if body.website_url_hp:
        return LeadInterestResponse()

    # 2. Strict rate limiting: 3 requests per IP / email per 10 minutes.
    client_ip = request.client.host if request.client else "unknown"
    normalized_email = body.email.strip().lower()
    await enforce_rate_limit(
        request,
        "lead_signup",
        f"{client_ip}:{normalized_email}",
        limit=3,
        window_seconds=600,
    )

    # 3. Parameterized DB write
    lead = Lead(
        email=normalized_email,
        company_name=body.company_name.strip() if body.company_name else None,
        phone=body.phone.strip() if body.phone else None,
        entities_count=body.entities_count,
        notes=body.notes.strip() if body.notes else None,
        status=LeadStatus.new,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(lead)
    await db.commit()

    return LeadInterestResponse()


# === Stealth Owner Lead Management ===


@router.get(
    "/api/v1/owner/leads",
    response_model=List[LeadOut],
)
async def list_owner_leads(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_internal_api_key: Annotated[str, Header()],
    status_filter: Optional[LeadStatus] = Query(None, alias="status"),
):
    """List all incoming leads for the owner."""
    _require_internal_key(x_internal_api_key)

    stmt = select(Lead).order_by(desc(Lead.created_at))
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch(
    "/api/v1/owner/leads/{lead_id}/status",
    response_model=LeadOut,
)
async def update_lead_status(
    lead_id: uuid.UUID,
    body: LeadStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_internal_api_key: Annotated[str, Header()],
):
    """Update lead status (contacted, converted, archived)."""
    _require_internal_key(x_internal_api_key)

    lead = (
        await db.execute(select(Lead).where(Lead.id == lead_id))
    ).scalar_one_or_none()

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    lead.status = body.status
    await db.commit()
    await db.refresh(lead)
    return lead


@router.post(
    "/api/v1/owner/leads/{lead_id}/provision",
    response_model=LeadProvisionResponse,
)
async def provision_company_from_lead(
    lead_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_internal_api_key: Annotated[str, Header()],
):
    """Owner provisions a new company and admin login from a lead."""
    _require_internal_key(x_internal_api_key)

    lead = (
        await db.execute(select(Lead).where(Lead.id == lead_id))
    ).scalar_one_or_none()

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    company_name = lead.company_name or f"Company ({lead.email.split('@')[0]})"
    admin_email = lead.email.strip().lower()

    # Check if user already exists
    existing = await db.execute(
        select(CompanyUser).where(
            func.lower(CompanyUser.email) == admin_email,
            CompanyUser.deleted_at.is_(None),
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email {admin_email} is already registered to a company",
        )

    # 1. Create company + mint activation key
    company = Company(name=company_name)
    activation_key = _mint_activation_key(company)
    db.add(company)
    await db.flush()

    # 2. Seed asset reference data
    from app.services.asset_seed import seed_global_asset_reference_data
    await seed_global_asset_reference_data(db, company_id=company.id)

    # 3. Generate company KEK
    _, encrypted_kek, nonce = generate_company_kek()
    company_key = CompanyKey(
        company_id=company.id,
        encrypted_kek=encrypted_kek,
        kek_nonce=nonce,
    )
    db.add(company_key)

    # 4. Create pending admin user
    user = CompanyUser(
        company_id=company.id,
        email=admin_email,
        hashed_password=PENDING_PASSWORD,
        role=UserRole.admin,
        is_active=False,
    )
    db.add(user)

    # 5. Mark lead as converted
    lead.status = LeadStatus.converted

    await db.commit()
    await db.refresh(company)

    return LeadProvisionResponse(
        lead_id=lead.id,
        company_id=company.id,
        company_name=company.name,
        admin_email=admin_email,
        activation_key=activation_key,
        activation_expires_at=company.activation_expires_at,
    )
