"""Depreciation calculation runs and lines router."""
import uuid
from decimal import Decimal
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_company_user, require_admin, require_assets_module
from app.models.company import CompanyUser
from app.models.depreciation import (
    DepreciationRun,
    DepreciationRunStatus,
    AssetDepreciationLine,
    ItBlockDepreciationLine,
)
from app.models.financial_year import FinancialYear
from app.schemas.depreciation import (
    DepreciationRunCreate,
    DepreciationRunReopenRequest,
    DepreciationRunResponse,
    AssetDepreciationLineResponse,
    ItBlockDepreciationLineResponse,
)
from app.services.activity import log_activity
from app.services.depreciation import DepreciationDataError
from app.services.depreciation_query import (
    DepreciationConflictError,
    FinancialYearNotFoundError,
    execute_depreciation_run,
    finalize_depreciation_run,
    reopen_depreciation_run,
)

router = APIRouter(prefix="/api/v1/depreciation", tags=["depreciation"])


def _populate_run_summary(run: DepreciationRun) -> DepreciationRunResponse:
    total_gb = sum((l.closing_gross_block for l in run.lines), Decimal("0.00"))
    total_dep = sum((l.depreciation_for_year for l in run.lines), Decimal("0.00"))
    total_nbv = sum((l.closing_carrying_amount for l in run.lines), Decimal("0.00"))

    total_it_dep = sum((l.total_depreciation for l in run.it_lines), Decimal("0.00"))
    total_it_wdv = sum((l.closing_wdv for l in run.it_lines), Decimal("0.00"))

    fy_label = run.financial_year.label if run.financial_year else ""

    return DepreciationRunResponse(
        id=run.id,
        company_id=run.company_id,
        financial_year_id=run.financial_year_id,
        financial_year_label=fy_label,
        book=run.book,
        run_date=run.run_date,
        status=run.status,
        finalized_at=run.finalized_at,
        finalized_by=run.finalized_by,
        notes=run.notes,
        total_gross_block=total_gb,
        total_depreciation=total_dep,
        total_carrying_amount=total_nbv,
        total_it_depreciation=total_it_dep,
        total_it_closing_wdv=total_it_wdv,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("/runs", response_model=List[DepreciationRunResponse])
async def list_depreciation_runs(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(DepreciationRun)
        .where(DepreciationRun.company_id == current_user.company_id)
        .options(
            selectinload(DepreciationRun.financial_year),
            selectinload(DepreciationRun.lines),
            selectinload(DepreciationRun.it_lines),
        )
        .order_by(DepreciationRun.run_date.desc())
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return [_populate_run_summary(r) for r in runs]


@router.post("/runs", response_model=DepreciationRunResponse, status_code=status.HTTP_201_CREATED)
async def create_depreciation_run(
    body: DepreciationRunCreate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        run = await execute_depreciation_run(
            db=db,
            company_id=current_user.company_id,
            financial_year_id=body.financial_year_id,
            user_id=current_user.id,
            notes=body.notes,
        )
    except FinancialYearNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DepreciationConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DepreciationDataError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    # Reload with relations
    stmt = (
        select(DepreciationRun)
        .where(DepreciationRun.id == run.id)
        .options(
            selectinload(DepreciationRun.financial_year),
            selectinload(DepreciationRun.lines),
            selectinload(DepreciationRun.it_lines),
        )
    )
    res = await db.execute(stmt)
    full_run = res.scalar_one()
    return _populate_run_summary(full_run)


@router.get("/runs/{run_id}", response_model=DepreciationRunResponse)
async def get_depreciation_run_detail(
    run_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(DepreciationRun)
        .where(
            and_(
                DepreciationRun.id == run_id,
                DepreciationRun.company_id == current_user.company_id,
            )
        )
        .options(
            selectinload(DepreciationRun.financial_year),
            selectinload(DepreciationRun.lines),
            selectinload(DepreciationRun.it_lines),
        )
    )
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Depreciation run not found")
    return _populate_run_summary(run)


@router.get("/runs/{run_id}/lines", response_model=List[AssetDepreciationLineResponse])
async def get_asset_depreciation_lines(
    run_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    run = await db.get(DepreciationRun, run_id)
    if not run or run.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Depreciation run not found")

    stmt = (
        select(AssetDepreciationLine)
        .where(AssetDepreciationLine.run_id == run_id)
        .order_by(AssetDepreciationLine.created_at.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/runs/{run_id}/it-lines", response_model=List[ItBlockDepreciationLineResponse])
async def get_it_block_depreciation_lines(
    run_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    run = await db.get(DepreciationRun, run_id)
    if not run or run.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Depreciation run not found")

    stmt = (
        select(ItBlockDepreciationLine)
        .where(ItBlockDepreciationLine.run_id == run_id)
        .order_by(ItBlockDepreciationLine.block_name.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/runs/{run_id}/finalize", response_model=DepreciationRunResponse)
async def finalize_run(
    run_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        run = await finalize_depreciation_run(
            db=db,
            company_id=current_user.company_id,
            run_id=run_id,
            user_id=current_user.id,
        )
    except DepreciationConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DepreciationDataError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except FinancialYearNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    stmt = (
        select(DepreciationRun)
        .where(DepreciationRun.id == run.id)
        .options(
            selectinload(DepreciationRun.financial_year),
            selectinload(DepreciationRun.lines),
            selectinload(DepreciationRun.it_lines),
        )
    )
    res = await db.execute(stmt)
    return _populate_run_summary(res.scalar_one())


@router.post("/runs/{run_id}/reopen", response_model=DepreciationRunResponse)
async def reopen_run(
    run_id: uuid.UUID,
    body: DepreciationRunReopenRequest,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        run = await reopen_depreciation_run(
            db, current_user.company_id, run_id, current_user.id, body.reason.strip()
        )
    # DepreciationConflictError subclasses ValueError, so it must be caught first.
    except DepreciationConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    await log_activity(db, current_user.company_id, current_user.id,
                       "depreciation.run.reopened", "depreciation_run", run.id,
                       {"reason": body.reason.strip()})
    await db.commit()

    # The service committed + refreshed, so run's relationships are stale; reload
    # with the same eager-load options as the other endpoints before summarizing.
    stmt = (
        select(DepreciationRun)
        .where(DepreciationRun.id == run.id)
        .options(
            selectinload(DepreciationRun.financial_year),
            selectinload(DepreciationRun.lines),
            selectinload(DepreciationRun.it_lines),
        )
    )
    res = await db.execute(stmt)
    return _populate_run_summary(res.scalar_one())


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_depreciation_run(
    run_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    run = await db.get(DepreciationRun, run_id)
    if not run or run.company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Depreciation run not found")

    if run.status == DepreciationRunStatus.finalized.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot delete a finalized depreciation run")

    await db.delete(run)
    await db.commit()
    return None
