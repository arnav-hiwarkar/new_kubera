"""Financial Year management endpoints."""
import uuid
from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_company_user, require_admin, require_assets_module
from app.models.company import CompanyUser
from app.models.financial_year import FinancialYear, FinancialYearStatus
from app.schemas.financial_years import FinancialYearCreate, FinancialYearResponse, FinancialYearReopenRequest
from app.services.activity import log_activity

router = APIRouter(
    prefix="/api/v1/financial-years",
    tags=["financial-years"],
    dependencies=[Depends(require_assets_module)],
)


@router.get("", response_model=List[FinancialYearResponse])
async def list_financial_years(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(FinancialYear)
        .where(FinancialYear.company_id == current_user.company_id)
        .order_by(FinancialYear.start_date.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=FinancialYearResponse, status_code=status.HTTP_201_CREATED)
async def create_financial_year(
    body: FinancialYearCreate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if body.start_date >= body.end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Start date must be before end date",
        )

    # Check unique label for company
    existing = await db.execute(
        select(FinancialYear).where(
            and_(
                FinancialYear.company_id == current_user.company_id,
                FinancialYear.label == body.label.strip(),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Financial year '{body.label}' already exists",
        )

    fy = FinancialYear(
        company_id=current_user.company_id,
        label=body.label.strip(),
        start_date=body.start_date,
        end_date=body.end_date,
        status=FinancialYearStatus.open.value,
    )
    db.add(fy)
    await db.commit()
    await db.refresh(fy)
    return fy


@router.post("/{fy_id}/close", response_model=FinancialYearResponse)
async def close_financial_year(
    fy_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    fy = await db.get(FinancialYear, fy_id)
    if not fy or fy.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")
    if fy.status == FinancialYearStatus.closed.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Financial year is already closed")

    fy.status = FinancialYearStatus.closed.value
    fy.closed_at = datetime.now(timezone.utc)
    fy.closed_by = current_user.id
    
    await log_activity(
        db, current_user.company_id, current_user.id,
        "financial_year.closed", "financial_year", fy.id,
        {"label": fy.label}
    )
    
    await db.commit()
    await db.refresh(fy)
    return fy


@router.post("/{fy_id}/reopen", response_model=FinancialYearResponse)
async def reopen_financial_year(
    fy_id: uuid.UUID,
    body: FinancialYearReopenRequest,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    fy = await db.get(FinancialYear, fy_id)
    if not fy or fy.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial year not found")
    if fy.status != FinancialYearStatus.closed.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Financial year is not closed")

    await log_activity(
        db, current_user.company_id, current_user.id,
        "financial_year.reopened", "financial_year", fy.id,
        {"reason": body.reason.strip(),
         "was_closed_at": fy.closed_at.isoformat() if fy.closed_at else None,
         "was_closed_by": str(fy.closed_by) if fy.closed_by else None}
    )

    fy.status = FinancialYearStatus.open.value
    fy.closed_at = None
    fy.closed_by = None
    await db.commit()
    await db.refresh(fy)
    return fy
