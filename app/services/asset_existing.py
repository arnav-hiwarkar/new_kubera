"""Creation logic shared by the single existing-asset form and the bulk import.

An 'existing' asset is one the company owned before this register (or before
the current year) — it carries opening balances instead of an acquisition
invoice. Validation here mirrors what depreciation_query will demand at run
time (and tightens it: books figures are required too) so mistakes surface at
entry rather than months later.
"""
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assets import Asset, AssetLifecycleStatus
from app.models.asset_masters import AssetCategory, AssetLookup
from app.models.financial_year import FinancialYear
from app.services.asset_register import apply_category_defaults
from app.services.asset_tags import allocate_asset_codes


class ExistingAssetError(ValueError):
    """Row-level rejection with a human message (HTTP 422 / import row error)."""


async def current_fy_start(db: AsyncSession, company_id: uuid.UUID) -> Optional[date]:
    """The FY containing today, or — when the company hasn't opened this year's
    FY yet — the latest FY already begun, which is where a backdated entry lands."""
    today = date.today()
    fy_start = (
        await db.execute(
            select(FinancialYear.start_date)
            .where(
                FinancialYear.company_id == company_id,
                FinancialYear.start_date <= today,
                FinancialYear.end_date >= today,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if fy_start is not None:
        return fy_start
    return (
        await db.execute(
            select(FinancialYear.start_date)
            .where(
                FinancialYear.company_id == company_id,
                FinancialYear.start_date <= today,
            )
            .order_by(FinancialYear.start_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def resolve_category_path(
    db: AsyncSession, company_id: uuid.UUID, path: list
) -> AssetCategory:
    """Resolve ['Parent', 'Child'] (child optional) case-insensitively against
    the company's own forked tree."""
    if not path or not str(path[0] or "").strip():
        raise ExistingAssetError("Category is required")
    parent_name = str(path[0]).strip().lower()
    parents = (
        await db.execute(
            select(AssetCategory).where(
                AssetCategory.company_id == company_id,
                AssetCategory.parent_id.is_(None),
                func.lower(AssetCategory.name) == parent_name,
            )
        )
    ).scalars().all()
    if len(parents) != 1:
        raise ExistingAssetError(f"Unknown category '{path[0]}'")

    child_raw = str(path[1]) if len(path) > 1 else ""
    if not child_raw.strip():
        return parents[0]

    children = (
        await db.execute(
            select(AssetCategory).where(
                AssetCategory.company_id == company_id,
                AssetCategory.parent_id == parents[0].id,
                func.lower(AssetCategory.name) == child_raw.strip().lower(),
            )
        )
    ).scalars().all()
    if len(children) != 1:
        raise ExistingAssetError(f"Unknown subcategory '{child_raw}' under '{path[0]}'")
    return children[0]


def _dec(value, field: str) -> Decimal:
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ExistingAssetError(f"{field} is not a valid amount")
    if d < 0:
        raise ExistingAssetError(f"{field} cannot be negative")
    return d


def validate_opening_values(
    *,
    original_cost: Decimal,
    opening_accumulated_depreciation: Optional[Decimal],
    opening_wdv: Optional[Decimal],
    opening_it_wdv: Optional[Decimal],
    put_to_use_date: Optional[date],
    capitalization_date: Optional[date],
    fy_start: Optional[date],
) -> None:
    cost = _dec(original_cost, "Original cost")
    for name, val in (
        ("Opening accumulated depreciation", opening_accumulated_depreciation),
        ("Opening WDV (books)", opening_wdv),
        ("Opening WDV (tax)", opening_it_wdv),
    ):
        if val is not None and _dec(val, name) > cost:
            raise ExistingAssetError(f"{name} cannot exceed original cost")

    effective = put_to_use_date or capitalization_date
    predates_fy = fy_start is not None and effective is not None and effective < fy_start
    undatable = fy_start is not None and effective is None
    if predates_fy or undatable:
        missing = [
            name for name, val in (
                ("Opening WDV (tax)", opening_it_wdv),
                ("Opening WDV (books)", opening_wdv),
                ("Opening accumulated depreciation", opening_accumulated_depreciation),
            ) if val is None
        ]
        if missing:
            raise ExistingAssetError(
                "Asset predates the current financial year: "
                + ", ".join(missing) + " required"
            )


async def build_existing_asset(
    db: AsyncSession,
    company_id: uuid.UUID,
    created_by: uuid.UUID,
    *,
    asset_name: str,
    category: AssetCategory,
    original_cost: Decimal,
    purchase_date: Optional[date] = None,
    put_to_use_date: Optional[date] = None,
    capitalization_date: Optional[date] = None,
    opening_accumulated_depreciation: Optional[Decimal] = None,
    opening_wdv: Optional[Decimal] = None,
    opening_it_wdv: Optional[Decimal] = None,
    useful_life_months: Optional[int] = None,
    residual_pct: Optional[Decimal] = None,
    branch_id: Optional[uuid.UUID] = None,
    location_id: Optional[uuid.UUID] = None,
    department_id: Optional[uuid.UUID] = None,
    cost_centre_id: Optional[uuid.UUID] = None,
    custodian_name: Optional[str] = None,
    serial_number: Optional[str] = None,
    remarks: Optional[str] = None,
) -> Asset:
    fy_start = await current_fy_start(db, company_id)
    validate_opening_values(
        original_cost=original_cost,
        opening_accumulated_depreciation=opening_accumulated_depreciation,
        opening_wdv=opening_wdv,
        opening_it_wdv=opening_it_wdv,
        put_to_use_date=put_to_use_date,
        capitalization_date=capitalization_date,
        fy_start=fy_start,
    )

    branch_code = None
    if branch_id is not None:
        branch_code = (
            await db.execute(select(AssetLookup.code).where(AssetLookup.id == branch_id))
        ).scalar_one_or_none()

    codes = await allocate_asset_codes(
        db, company_id, category.tag_prefix, 1, branch_code=branch_code
    )
    unit = Asset(
        company_id=company_id,
        unit_index=1,
        asset_code=codes[0],
        asset_name=asset_name.strip(),
        category_id=category.id,
        lifecycle_status=AssetLifecycleStatus.draft,
        is_pre_cutover=True,
        original_cost=original_cost,
        manufacturer_serial_number=serial_number,
        it_put_to_use_date=put_to_use_date,
        capitalization_date=capitalization_date,
        available_for_use_date=None,
        opening_accumulated_depreciation=opening_accumulated_depreciation,
        opening_wdv=opening_wdv,
        opening_it_wdv=opening_it_wdv,
        branch_id=branch_id,
        location_id=location_id,
        department_id=department_id,
        cost_centre_id=cost_centre_id,
        custodian_name=custodian_name,
        remarks=remarks,
        created_by=created_by,
        custom_fields={},
    )
    await apply_category_defaults(db, unit, category.id)
    # Explicit inputs win over defaults; deviating from the Schedule II life
    # needs the statutory disclosure reason.
    if useful_life_months is not None:
        if unit.useful_life_months and useful_life_months != unit.useful_life_months \
                and not unit.useful_life_override_reason:
            raise ExistingAssetError(
                "Useful life differs from the category default — supply "
                "useful_life_override_reason"
            )
        unit.useful_life_months = useful_life_months
    if residual_pct is not None:
        unit.residual_pct = residual_pct
    db.add(unit)
    await db.flush()
    return unit
