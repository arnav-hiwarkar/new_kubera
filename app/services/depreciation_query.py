"""Database query and orchestration layer for depreciation calculations."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import select, and_, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assets import Asset, AssetLifecycleStatus
from app.models.asset_masters import ItAssetBlock, DepreciationMethod
from app.models.financial_year import FinancialYear
from app.models.depreciation import (
    DepreciationBook,
    DepreciationRun,
    DepreciationRunStatus,
    AssetDepreciationLine,
    ItBlockDepreciationLine,
)
from app.services.depreciation import (
    AssetDepreciationInput,
    DepreciationDataError,
    calculate_asset_depreciation,
)
from app.services.it_depreciation import (
    ItBlockDepreciationInput,
    calculate_it_block_depreciation,
)


class DepreciationConflictError(ValueError):
    """Raised when sequence/status gating rules are violated (HTTP 409)."""
    pass


class FinancialYearNotFoundError(ValueError):
    """Raised when the financial year is not found (HTTP 404)."""
    pass


async def _load_prior_run_lines(
    db: AsyncSession, company_id: uuid.UUID, fy_start: date, fy_label: str
):
    """Opening balances come from the prior FY's finalized run. A block's tax WDV is not
    asset-attributable after year one, so it cannot be reconstructed any other way."""
    prior_fy = (
        await db.execute(
            select(FinancialYear)
            .where(
                FinancialYear.company_id == company_id,
                FinancialYear.end_date < fy_start,
            )
            .order_by(FinancialYear.end_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if prior_fy is None:
        return {}, {}

    prior_run = (
        await db.execute(
            select(DepreciationRun)
            .where(
                DepreciationRun.company_id == company_id,
                DepreciationRun.financial_year_id == prior_fy.id,
                DepreciationRun.status == DepreciationRunStatus.finalized.value,
            )
            .order_by(DepreciationRun.finalized_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if prior_run is None:
        # Check if an unfinalized (draft) run exists for prior FY
        draft_run = (
            await db.execute(
                select(DepreciationRun)
                .where(
                    and_(
                        DepreciationRun.company_id == company_id,
                        DepreciationRun.financial_year_id == prior_fy.id,
                        DepreciationRun.status == DepreciationRunStatus.draft.value,
                    )
                )
                .limit(1)
            )
        ).scalars().first()
        if draft_run is not None:
            raise DepreciationConflictError(
                f"Depreciation for {prior_fy.label} must be finalized before running {fy_label}."
            )

        # Check via SQL EXISTS if assets were capitalized or available before fy_start that are not pre-cutover
        eff_date = func.coalesce(Asset.capitalization_date, Asset.available_for_use_date)
        has_prior_cap_assets = (
            await db.execute(
                select(
                    select(Asset.id)
                    .where(
                        and_(
                            Asset.company_id == company_id,
                            Asset.lifecycle_status.in_([
                                AssetLifecycleStatus.capitalized,
                                AssetLifecycleStatus.disposed,
                            ]),
                            Asset.is_pre_cutover.is_(False),
                            eff_date < fy_start,
                        )
                    )
                    .exists()
                )
            )
        ).scalar()
        if has_prior_cap_assets:
            raise DepreciationConflictError(
                f"No depreciation run exists for prior financial year {prior_fy.label}. Please run and finalize depreciation for {prior_fy.label} before running {fy_label}."
            )

        return {}, {}

    asset_lines = (
        await db.execute(
            select(AssetDepreciationLine).where(
                AssetDepreciationLine.run_id == prior_run.id
            )
        )
    ).scalars().all()
    block_lines = (
        await db.execute(
            select(ItBlockDepreciationLine).where(
                ItBlockDepreciationLine.run_id == prior_run.id
            )
        )
    ).scalars().all()
    return (
        {l.asset_id: l for l in asset_lines},
        {l.it_block_id: l for l in block_lines},
    )


async def execute_depreciation_run(
    db: AsyncSession,
    company_id: uuid.UUID,
    financial_year_id: uuid.UUID,
    book: str = "companies_act",
    user_id: Optional[uuid.UUID] = None,
    notes: Optional[str] = None,
) -> DepreciationRun:
    """Executes full Companies Act and Income Tax depreciation for a financial year."""
    fy = await db.get(FinancialYear, financial_year_id)
    if not fy or fy.company_id != company_id:
        raise FinancialYearNotFoundError("Financial year not found")

    fy_start: date = fy.start_date
    fy_end: date = fy.end_date

    # Load prior finalized run lines for carry-forward balances (with F9 gating)
    prior_asset_lines, prior_block_lines = await _load_prior_run_lines(
        db, company_id, fy_start, fy.label
    )

    # Supersede any existing draft run for this FY and book
    await db.execute(
        delete(DepreciationRun).where(
            and_(
                DepreciationRun.company_id == company_id,
                DepreciationRun.financial_year_id == financial_year_id,
                DepreciationRun.book == book,
                DepreciationRun.status == DepreciationRunStatus.draft.value,
            )
        )
    )

    # 1. Query all assets eligible for depreciation:
    # - Capitalized or Disposed
    # - Capitalization date <= fy_end or pre-cutover
    stmt = (
        select(Asset)
        .where(
            and_(
                Asset.company_id == company_id,
                Asset.lifecycle_status.in_([AssetLifecycleStatus.capitalized, AssetLifecycleStatus.disposed]),
            )
        )
        .options(selectinload(Asset.category), selectinload(Asset.it_block))
    )
    res = await db.execute(stmt)
    assets = list(res.scalars().all())

    # Create draft run
    run = DepreciationRun(
        company_id=company_id,
        financial_year_id=financial_year_id,
        book=book,
        run_date=datetime.now(timezone.utc),
        status=DepreciationRunStatus.draft.value,
        notes=notes,
    )
    db.add(run)
    await db.flush()

    # 2. Companies Act Asset-wise Calculation
    asset_lines: List[AssetDepreciationLine] = []
    for asset in assets:
        # Exclude assets capitalized after this FY end
        cap_date = asset.capitalization_date or asset.available_for_use_date
        if cap_date and cap_date > fy_end:
            continue
        # Exclude assets disposed before this FY start
        if asset.disposal_date and asset.disposal_date < fy_start:
            continue

        if asset.useful_life_months is None:
            raise DepreciationDataError(
                f"Asset {asset.id} ({asset.asset_name}) has no useful life specified"
            )
        months = asset.useful_life_months

        cost = asset.original_cost if asset.original_cost is not None else Decimal("0.00")
        residual_pct = asset.residual_pct if asset.residual_pct is not None else Decimal("5.00")
        method = "WDV" if asset.dep_method == DepreciationMethod.wdv else "SLM"

        # Opening accumulated depreciation:
        # Prior finalized run closing accumulated dep if present,
        # else asset cutover field,
        # else zero.
        if asset.id in prior_asset_lines:
            opening_acc = prior_asset_lines[asset.id].closing_accumulated_depreciation
        elif asset.opening_accumulated_depreciation is not None:
            opening_acc = asset.opening_accumulated_depreciation
        else:
            opening_acc = Decimal("0.00")

        inp = AssetDepreciationInput(
            asset_id=str(asset.id),
            asset_name=asset.asset_name,
            original_cost=cost,
            capitalization_date=cap_date,
            useful_life_months=months,
            residual_pct=residual_pct,
            residual_value=asset.residual_value,
            dep_method=method,
            opening_accumulated_dep=opening_acc,
            disposal_date=asset.disposal_date,
            disposal_type=asset.disposal_type,
            sale_proceeds=asset.sale_proceeds,
            is_pre_cutover=asset.is_pre_cutover,
        )

        calc = calculate_asset_depreciation(inp, fy_start, fy_end)

        line = AssetDepreciationLine(
            run_id=run.id,
            asset_id=asset.id,
            method=calc.method,
            opening_gross_block=calc.opening_gross_block,
            additions=calc.additions,
            disposals=calc.disposals,
            closing_gross_block=calc.closing_gross_block,
            opening_accumulated_depreciation=calc.opening_accumulated_dep,
            depreciation_for_year=calc.depreciation_for_year,
            disposal_accumulated_depreciation=calc.disposal_accumulated_dep,
            closing_accumulated_depreciation=calc.closing_accumulated_dep,
            opening_carrying_amount=calc.opening_carrying_amount,
            closing_carrying_amount=calc.closing_carrying_amount,
            residual_value=calc.residual_value,
            remaining_useful_life_days=calc.remaining_useful_life_days,
            effective_rate_pct=calc.effective_rate_pct,
            is_part_year=calc.is_part_year,
            is_disposed=calc.is_disposed,
            gain_loss_on_disposal=calc.gain_loss_on_disposal,
        )
        db.add(line)
        asset_lines.append(line)

    # 3. Income Tax Act Block-wise Calculation
    # Fetch all IT blocks for the company (including global reference blocks)
    block_stmt = select(ItAssetBlock).where(
        (ItAssetBlock.company_id == company_id) | (ItAssetBlock.company_id.is_(None))
    )
    block_res = await db.execute(block_stmt)
    it_blocks = list(block_res.scalars().all())

    # Map assets to blocks
    assets_by_block = {}
    for a in assets:
        if a.it_block_id:
            assets_by_block.setdefault(a.it_block_id, []).append(a)

    it_lines: List[ItBlockDepreciationLine] = []

    for block in it_blocks:
        block_assets = assets_by_block.get(block.id, [])
        rate = Decimal(str(block.dep_rate)) if block.dep_rate is not None else Decimal("15.00")

        # Aggregate additions >= 180 days, additions < 180 days, and sales
        add_more = Decimal("0.00")
        add_less = Decimal("0.00")
        sales = Decimal("0.00")
        has_active_assets = False

        if block.id in prior_block_lines:
            opening_wdv = prior_block_lines[block.id].closing_wdv
        else:
            opening_wdv = Decimal("0.00")
            for a in block_assets:
                if a.disposal_date and a.disposal_date < fy_start:
                    continue
                cap_date = a.it_put_to_use_date or a.capitalization_date or a.available_for_use_date
                if cap_date and cap_date < fy_start:
                    if a.opening_it_wdv is not None:
                        opening_wdv += a.opening_it_wdv
                    elif a.opening_wdv is not None:
                        opening_wdv += a.opening_wdv
                    elif a.is_pre_cutover:
                        raise DepreciationDataError(
                            f"Asset {a.id} ({a.asset_name}) is pre-cutover but has no opening_it_wdv or opening_wdv set"
                        )

        active_or_current_assets = [
            a for a in block_assets
            if not (a.disposal_date and a.disposal_date < fy_start)
        ]

        for a in active_or_current_assets:
            cap_date = a.it_put_to_use_date or a.capitalization_date or a.available_for_use_date

            # Check additions during FY
            if cap_date and fy_start <= cap_date <= fy_end:
                days_put = (fy_end - cap_date).days + 1
                cost = a.original_cost if a.original_cost is not None else Decimal("0.00")
                if days_put >= 180:
                    add_more += cost
                else:
                    add_less += cost

            # Check sales during FY
            if a.disposal_date and fy_start <= a.disposal_date <= fy_end:
                proceeds = a.disposal_it_proceeds if a.disposal_it_proceeds is not None else (a.sale_proceeds if a.sale_proceeds is not None else Decimal("0.00"))
                sales += proceeds
            elif not a.disposal_date or a.disposal_date > fy_end:
                has_active_assets = True

        all_disposed = (len(active_or_current_assets) > 0) and (not has_active_assets)

        it_inp = ItBlockDepreciationInput(
            block_id=str(block.id),
            block_name=block.name,
            prescribed_rate=rate,
            opening_wdv=opening_wdv,
            additions_more_than_180=add_more,
            additions_less_than_180=add_less,
            realized_from_sales=sales,
            all_assets_disposed=all_disposed,
        )

        it_calc = calculate_it_block_depreciation(it_inp)

        it_line = ItBlockDepreciationLine(
            run_id=run.id,
            it_block_id=block.id,
            block_name=block.name,
            prescribed_rate=it_calc.prescribed_rate,
            opening_wdv=it_calc.opening_wdv,
            additions_more_than_180=it_calc.additions_more_than_180,
            additions_less_than_180=it_calc.additions_less_than_180,
            realized_from_sales=it_calc.realized_from_sales,
            balance_before_depreciation=it_calc.balance_before_depreciation,
            depreciation_full_rate=it_calc.depreciation_full_rate,
            depreciation_half_rate=it_calc.depreciation_half_rate,
            total_depreciation=it_calc.total_depreciation,
            closing_wdv=it_calc.closing_wdv,
            capital_gain_or_loss=it_calc.capital_gain_or_loss,
            has_stcg=it_calc.has_stcg,
            has_stcl=it_calc.has_stcl,
        )
        db.add(it_line)
        it_lines.append(it_line)

    await db.commit()
    await db.refresh(run)
    return run


async def finalize_depreciation_run(
    db: AsyncSession,
    company_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DepreciationRun:
    """Finalize a depreciation run, locking its calculations for statutory reporting."""
    run = await db.get(DepreciationRun, run_id)
    if not run or run.company_id != company_id:
        raise ValueError("Depreciation run not found")

    # Check partial uniqueness before finalizing
    existing_finalized = (
        await db.execute(
            select(DepreciationRun)
            .where(
                and_(
                    DepreciationRun.company_id == company_id,
                    DepreciationRun.financial_year_id == run.financial_year_id,
                    DepreciationRun.status == DepreciationRunStatus.finalized.value,
                    DepreciationRun.id != run.id,
                )
            )
            .limit(1)
        )
    ).scalars().first()
    if existing_finalized:
        raise DepreciationConflictError(
            f"A finalized depreciation run already exists for this financial year."
        )

    run.status = DepreciationRunStatus.finalized.value
    run.finalized_at = datetime.now(timezone.utc)
    run.finalized_by = user_id
    await db.commit()
    await db.refresh(run)
    return run

