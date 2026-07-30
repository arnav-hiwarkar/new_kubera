"""Register operations that span an acquisition and its asset units.

Two things live here because both need the acquisition and all of its units at
once:

  explode_acquisition — turn one invoice line for N identical items into N
      individually tagged, individually depreciable asset rows.
  recompute_acquisition_costs — re-run the costing arithmetic and re-allocate the
      per-unit cost so the units always sum exactly to the landed cost.
"""
import uuid
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_masters import (
    AssetCategory,
    AssetLookup,
    DiscountType,
    ItcTreatment,
    Supplier,
)
from app.models.assets import (
    Asset,
    AssetAcquisition,
    AssetLifecycleStatus,
)
from app.models.company import Company
from app.services.asset_costing import (
    AcquisitionCostInput,
    compute_acquisition_cost,
    compute_residual_value,
    compute_warranty_expiry,
)
from app.services.asset_tags import allocate_asset_codes


async def resolve_place_of_supply(
    db: AsyncSession, company_id: uuid.UUID, branch_id: Optional[uuid.UUID]
) -> Optional[str]:
    """State code that receives the supply: the branch's if it has its own GST
    registration, else the company's."""
    if branch_id is not None:
        branch = (
            await db.execute(select(AssetLookup).where(AssetLookup.id == branch_id))
        ).scalar_one_or_none()
        if branch is not None and branch.state_code:
            return branch.state_code
    company = (
        await db.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is not None and company.gstin:
        return company.gstin[:2]
    return None


async def recompute_acquisition_costs(
    db: AsyncSession,
    acquisition: AssetAcquisition,
    units: Optional[Sequence[Asset]] = None,
) -> None:
    """Recompute every derived money field on `acquisition` and push the allocated
    per-unit cost onto its units. Does not commit.

    Capitalized units are left alone: their cost is locked, and a change after
    capitalization has to go through an explicit cost adjustment (P2) so the
    depreciation already charged stays explainable.
    """
    supplier_state = None
    if acquisition.supplier_id is not None:
        supplier = (
            await db.execute(select(Supplier).where(Supplier.id == acquisition.supplier_id))
        ).scalar_one_or_none()
        if supplier is not None:
            supplier_state = supplier.state_code
            # Snapshot so the register does not shift when the master is edited.
            acquisition.supplier_name_snapshot = supplier.name
            acquisition.supplier_gstin_snapshot = supplier.gstin

    if acquisition.place_of_supply_state_code is None:
        acquisition.place_of_supply_state_code = await resolve_place_of_supply(
            db, acquisition.company_id, acquisition.branch_id
        )

    overrides = {}
    if acquisition.gst_amounts_overridden:
        overrides = {
            "cgst_amount_override": acquisition.cgst_amount,
            "sgst_amount_override": acquisition.sgst_amount,
            "igst_amount_override": acquisition.igst_amount,
        }

    breakdown = compute_acquisition_cost(
        AcquisitionCostInput(
            quantity=acquisition.quantity or 1,
            unit_basic_price=acquisition.unit_basic_price or Decimal("0"),
            discount_type=acquisition.discount_type or DiscountType.amount,
            discount_value=acquisition.discount_value or Decimal("0"),
            gst_rate=acquisition.gst_rate or Decimal("0"),
            supplier_state_code=supplier_state,
            place_of_supply_state_code=acquisition.place_of_supply_state_code,
            itc_treatment=acquisition.itc_treatment or ItcTreatment.eligible,
            itc_eligible_pct=acquisition.itc_eligible_pct,
            freight_cost=acquisition.freight_cost or Decimal("0"),
            installation_cost=acquisition.installation_cost or Decimal("0"),
            other_capitalizable_cost=acquisition.other_capitalizable_cost or Decimal("0"),
            **overrides,
        )
    )

    acquisition.gross_basic_price = breakdown.gross_basic_price
    acquisition.discount_amount = breakdown.discount_amount
    acquisition.net_basic_price = breakdown.net_basic_price
    acquisition.gst_split_basis = breakdown.gst_split_basis
    if not acquisition.gst_amounts_overridden:
        acquisition.cgst_amount = breakdown.cgst_amount
        acquisition.sgst_amount = breakdown.sgst_amount
        acquisition.igst_amount = breakdown.igst_amount
    acquisition.total_gst = breakdown.total_gst
    acquisition.recoverable_gst = breakdown.recoverable_gst
    acquisition.capitalizable_gst = breakdown.capitalizable_gst
    acquisition.landed_cost = breakdown.landed_cost
    acquisition.total_acquisition_outlay = breakdown.total_acquisition_outlay
    acquisition.per_unit_cost = breakdown.per_unit_cost

    if units is None:
        units = (
            (
                await db.execute(
                    select(Asset)
                    .where(Asset.acquisition_id == acquisition.id)
                    .order_by(Asset.unit_index)
                )
            )
            .scalars()
            .all()
        )

    allocation = breakdown.unit_cost_allocation
    for unit in sorted(units, key=lambda u: u.unit_index or 0):
        if unit.lifecycle_status in (
            AssetLifecycleStatus.capitalized,
            AssetLifecycleStatus.disposed,
        ):
            continue
        idx = (unit.unit_index or 1) - 1
        if 0 <= idx < len(allocation):
            unit.original_cost = allocation[idx]
        refresh_derived_asset_fields(unit)


def refresh_derived_asset_fields(asset: Asset) -> None:
    """Recompute the unit-level derived fields (residual amount, warranty expiry)."""
    asset.residual_value = compute_residual_value(asset.original_cost, asset.residual_pct)
    asset.warranty_expiry_date = compute_warranty_expiry(
        asset.warranty_start_date, asset.warranty_months
    )


async def apply_category_defaults(db: AsyncSession, asset: Asset, category_id: uuid.UUID) -> None:
    """Copy the category's statutory defaults onto an asset, without clobbering
    anything the user has already set. This is what keeps the create form short:
    picking a category fills useful life, method, residual, IT block and rate.
    """
    category = (
        await db.execute(select(AssetCategory).where(AssetCategory.id == category_id))
    ).scalars().unique().one_or_none()
    if category is None:
        return
    if asset.useful_life_months is None:
        asset.useful_life_months = category.default_useful_life_months
    if asset.dep_method is None:
        asset.dep_method = category.default_dep_method
    if asset.residual_pct is None:
        asset.residual_pct = category.default_residual_pct
    if asset.it_block_id is None:
        asset.it_block_id = category.default_it_block_id
    if asset.it_dep_rate is None and category.it_block is not None:
        asset.it_dep_rate = category.it_block.dep_rate


async def explode_acquisition(
    db: AsyncSession,
    acquisition: AssetAcquisition,
    *,
    asset_name: str,
    category_id: uuid.UUID,
    created_by: uuid.UUID,
    branch_id: Optional[uuid.UUID] = None,
    extra: Optional[dict] = None,
) -> list[Asset]:
    """Create `acquisition.quantity` draft asset units, each individually tagged.

    Each unit gets its own row precisely so that partial disposal, per-unit
    location and per-unit depreciation are possible later without a data migration.
    """
    category = (
        await db.execute(select(AssetCategory).where(AssetCategory.id == category_id))
    ).scalars().unique().one_or_none()

    branch_code = None
    if branch_id is not None:
        branch = (
            await db.execute(select(AssetLookup).where(AssetLookup.id == branch_id))
        ).scalar_one_or_none()
        if branch is not None:
            branch_code = branch.code

    quantity = acquisition.quantity or 1
    codes = await allocate_asset_codes(
        db,
        acquisition.company_id,
        category.tag_prefix if category else None,
        quantity,
        branch_code=branch_code,
    )

    units: list[Asset] = []
    for i in range(quantity):
        unit = Asset(
            company_id=acquisition.company_id,
            acquisition_id=acquisition.id,
            unit_index=i + 1,
            asset_code=codes[i],
            asset_name=asset_name,
            category_id=category_id,
            branch_id=branch_id,
            lifecycle_status=AssetLifecycleStatus.draft,
            created_by=created_by,
            custom_fields={},
            **(extra or {}),
        )
        await apply_category_defaults(db, unit, category_id)
        db.add(unit)
        units.append(unit)

    await db.flush()
    await recompute_acquisition_costs(db, acquisition, units)
    return units
