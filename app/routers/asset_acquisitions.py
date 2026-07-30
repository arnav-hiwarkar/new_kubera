"""Acquisition (invoice line) endpoints.

Deliberately a separate prefix from /api/v1/assets rather than a nested literal
path, so it can never be shadowed by the /{asset_id} route.

Every write recomputes the derived cost fields and re-allocates the per-unit cost,
so the units always sum back to the landed cost exactly.
"""
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_assets_module
from app.database import get_db
from app.models.asset_masters import Supplier
from app.models.assets import Asset, AssetAcquisition, AssetLifecycleStatus
from app.models.company import CompanyUser
from app.schemas.assets import (
    AcquisitionResponse,
    AcquisitionUpdate,
    AssetResponse,
)
from app.services.activity import log_activity
from app.services.asset_register import (
    explode_acquisition,
    recompute_acquisition_costs,
    resolve_place_of_supply,
)

router = APIRouter(prefix="/api/v1/asset-acquisitions", tags=["assets"])

Reader = Annotated[CompanyUser, Depends(require_assets_module)]
Db = Annotated[AsyncSession, Depends(get_db)]

# Changing any of these changes the capitalized cost, so they are frozen once any
# unit under the acquisition is on the books.
COST_AFFECTING_FIELDS = frozenset(
    {
        "quantity",
        "unit_basic_price",
        "discount_type",
        "discount_value",
        "gst_rate",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "gst_amounts_overridden",
        "itc_treatment",
        "itc_eligible_pct",
        "freight_cost",
        "installation_cost",
        "other_capitalizable_cost",
        "supplier_id",
        "branch_id",
        "place_of_supply_state_code",
    }
)


async def _load(acq_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession) -> AssetAcquisition:
    result = await db.execute(
        select(AssetAcquisition)
        .options(selectinload(AssetAcquisition.units))
        .where(AssetAcquisition.id == acq_id, AssetAcquisition.company_id == company_id)
    )
    acq = result.scalars().unique().one_or_none()
    if acq is None:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    return acq


@router.get("", response_model=List[AcquisitionResponse])
async def list_acquisitions(current_user: Reader, db: Db, supplier_id: Optional[uuid.UUID] = None):
    query = select(AssetAcquisition).where(
        AssetAcquisition.company_id == current_user.company_id
    )
    if supplier_id is not None:
        query = query.where(AssetAcquisition.supplier_id == supplier_id)
    result = await db.execute(query.order_by(AssetAcquisition.created_at.desc()))
    return result.scalars().unique().all()


@router.get("/{acq_id}", response_model=AcquisitionResponse)
async def get_acquisition(acq_id: uuid.UUID, current_user: Reader, db: Db):
    return await _load(acq_id, current_user.company_id, db)


@router.get("/{acq_id}/units", response_model=List[AssetResponse])
async def list_acquisition_units(acq_id: uuid.UUID, current_user: Reader, db: Db):
    await _load(acq_id, current_user.company_id, db)
    result = await db.execute(
        select(Asset)
        .where(Asset.acquisition_id == acq_id, Asset.company_id == current_user.company_id)
        .order_by(Asset.unit_index)
    )
    return result.scalars().unique().all()


@router.patch("/{acq_id}", response_model=AcquisitionResponse)
async def update_acquisition(
    acq_id: uuid.UUID, body: AcquisitionUpdate, current_user: Reader, db: Db
):
    acq = await _load(acq_id, current_user.company_id, db)
    update = body.model_dump(exclude_unset=True)

    locked_units = [
        u
        for u in acq.units
        if u.lifecycle_status in (AssetLifecycleStatus.capitalized, AssetLifecycleStatus.disposed)
    ]
    if locked_units:
        offending = sorted(set(update) & COST_AFFECTING_FIELDS)
        if offending:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Cost fields are locked because assets from this acquisition are already "
                        "capitalized. Record a cost adjustment instead."
                    ),
                    "locked_fields": offending,
                    "capitalized_assets": [str(u.id) for u in locked_units],
                },
            )

    if "supplier_id" in update and update["supplier_id"] is not None:
        exists = await db.execute(
            select(Supplier.id).where(
                Supplier.id == update["supplier_id"],
                Supplier.company_id == current_user.company_id,
            )
        )
        if exists.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Invalid supplier_id")

    new_quantity = update.pop("quantity", None)

    # Explicitly typed GST amounts must survive a later recompute.
    if {"cgst_amount", "sgst_amount", "igst_amount"} & set(update) and "gst_amounts_overridden" not in update:
        update["gst_amounts_overridden"] = True

    branch_changed = "branch_id" in update and update["branch_id"] != acq.branch_id

    for key, value in update.items():
        setattr(acq, key, value)

    if branch_changed:
        # Re-derive place of supply from the new branch, which may flip the entry
        # between CGST+SGST and IGST.
        acq.place_of_supply_state_code = await resolve_place_of_supply(
            db, acq.company_id, acq.branch_id
        )

    if new_quantity is not None and new_quantity != acq.quantity:
        await _resize(db, acq, new_quantity, current_user)
    else:
        await recompute_acquisition_costs(db, acq, acq.units)

    await log_activity(
        db,
        current_user.company_id,
        current_user.id,
        "asset_acquisition.updated",
        "asset_acquisition",
        acq.id,
        {"fields": sorted(set(update) | ({"quantity"} if new_quantity is not None else set()))},
    )
    await db.commit()
    return await _load(acq_id, current_user.company_id, db)


async def _resize(
    db: AsyncSession, acq: AssetAcquisition, new_quantity: int, current_user: CompanyUser
) -> None:
    """Grow or shrink an exploded batch.

    Growing mints new tags for the extra units. Shrinking removes trailing DRAFT
    units only — a capitalized unit is on the books and cannot vanish because
    somebody edited the invoice quantity.
    """
    units = sorted(acq.units, key=lambda u: u.unit_index or 0)
    current = len(units)

    if new_quantity > current:
        anchor = units[0] if units else None
        acq.quantity = new_quantity
        extra = new_quantity - current
        from app.services.asset_tags import allocate_asset_codes

        category_id = anchor.category_id if anchor else None
        prefix = anchor.category.tag_prefix if anchor and anchor.category else None
        codes = await allocate_asset_codes(db, acq.company_id, prefix, extra)
        for i in range(extra):
            unit = Asset(
                company_id=acq.company_id,
                acquisition_id=acq.id,
                unit_index=current + i + 1,
                asset_code=codes[i],
                asset_name=anchor.asset_name if anchor else "Asset",
                category_id=category_id,
                branch_id=acq.branch_id,
                lifecycle_status=AssetLifecycleStatus.draft,
                created_by=current_user.id,
                custom_fields={},
            )
            if category_id is not None:
                from app.services.asset_register import apply_category_defaults

                await apply_category_defaults(db, unit, category_id)
            db.add(unit)
        await db.flush()
    elif new_quantity < current:
        removable = [
            u for u in units[new_quantity:] if u.lifecycle_status == AssetLifecycleStatus.draft
        ]
        if len(removable) < current - new_quantity:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Cannot reduce the quantity: some of the units being removed are no longer "
                    "drafts. Dispose of them instead."
                ),
            )
        for unit in removable:
            await db.delete(unit)
        acq.quantity = new_quantity
        await db.flush()

    fresh = (
        (
            await db.execute(
                select(Asset).where(Asset.acquisition_id == acq.id).order_by(Asset.unit_index)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    # Re-index so unit_index stays 1..N with no gaps after a shrink.
    for i, unit in enumerate(sorted(fresh, key=lambda u: u.unit_index or 0), start=1):
        unit.unit_index = i
    await db.flush()
    await recompute_acquisition_costs(db, acq, fresh)


@router.post("/{acq_id}/explode", response_model=List[AssetResponse])
async def explode(acq_id: uuid.UUID, current_user: Reader, db: Db):
    """Re-create missing units for an acquisition (recovery path — normal creation
    explodes automatically in quick-add)."""
    acq = await _load(acq_id, current_user.company_id, db)
    if acq.units:
        raise HTTPException(status_code=409, detail="This acquisition already has units")
    anchor_name = "Asset"
    units = await explode_acquisition(
        db,
        acq,
        asset_name=anchor_name,
        category_id=None,
        created_by=current_user.id,
        branch_id=acq.branch_id,
    )
    await db.commit()
    return units
