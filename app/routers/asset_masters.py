"""Fixed-asset master data endpoints.

Reads require the `assets` module; writes require admin. Seeded global rows
(company_id IS NULL) are visible to every tenant but not editable by them.
"""
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, require_assets_module
from app.database import get_db
from app.models.asset_masters import (
    AssetCategory,
    AssetLookup,
    AssetLookupKind,
    ItAssetBlock,
    Supplier,
)
from app.models.company import CompanyUser
from app.schemas.asset_masters import (
    AssetCategoryCreate,
    AssetCategoryResponse,
    AssetCategoryUpdate,
    AssetLookupCreate,
    AssetLookupResponse,
    AssetLookupUpdate,
    ItAssetBlockCreate,
    ItAssetBlockResponse,
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)

router = APIRouter(prefix="/api/v1/asset-masters", tags=["asset-masters"])

CurrentReader = Annotated[CompanyUser, Depends(require_assets_module)]
CurrentAdmin = Annotated[CompanyUser, Depends(require_admin)]
Db = Annotated[AsyncSession, Depends(get_db)]


def _state_code_from_gstin(gstin: Optional[str]) -> Optional[str]:
    """First two digits of a GSTIN are the state code — what place-of-supply
    comparisons actually use."""
    return gstin[:2] if gstin else None


# === IT asset blocks ===

@router.get("/it-blocks", response_model=List[ItAssetBlockResponse])
async def list_it_blocks(current_user: CurrentReader, db: Db):
    from app.services.asset_seed import ensure_company_masters_forked
    await ensure_company_masters_forked(db, current_user.company_id)

    result = await db.execute(
        select(ItAssetBlock)
        .where(
            or_(
                ItAssetBlock.company_id.is_(None),
                ItAssetBlock.company_id == current_user.company_id,
            )
        )
        .order_by(ItAssetBlock.display_order, ItAssetBlock.code)
    )
    return result.scalars().all()


@router.post("/it-blocks", response_model=ItAssetBlockResponse, status_code=status.HTTP_201_CREATED)
async def create_it_block(body: ItAssetBlockCreate, current_user: CurrentAdmin, db: Db):
    block = ItAssetBlock(company_id=current_user.company_id, **body.model_dump())
    db.add(block)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A block with this code already exists")
    await db.refresh(block)
    return block


# === Categories ===

@router.get("/categories", response_model=List[AssetCategoryResponse])
async def list_categories(current_user: CurrentReader, db: Db, include_inactive: bool = False):
    from app.services.asset_seed import ensure_company_masters_forked
    await ensure_company_masters_forked(db, current_user.company_id)

    query = select(AssetCategory).where(
        or_(
            AssetCategory.company_id.is_(None),
            AssetCategory.company_id == current_user.company_id,
        )
    )
    if not include_inactive:
        query = query.where(AssetCategory.is_active.is_(True))
    result = await db.execute(query.order_by(AssetCategory.display_order, AssetCategory.name))
    return result.scalars().unique().all()


async def _load_category_for_write(
    category_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession
) -> AssetCategory:
    result = await db.execute(select(AssetCategory).where(AssetCategory.id == category_id))
    cat = result.scalars().unique().one_or_none()
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
    if cat.company_id is None:
        raise HTTPException(
            status_code=403,
            detail="This is a seeded global category. Create your own category instead of editing it.",
        )
    if cat.company_id != company_id:
        raise HTTPException(status_code=404, detail="Category not found")
    return cat


@router.post("/categories", response_model=AssetCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(body: AssetCategoryCreate, current_user: CurrentAdmin, db: Db):
    if body.parent_id is not None:
        parent_res = await db.execute(
            select(AssetCategory).where(
                AssetCategory.id == body.parent_id,
                or_(
                    AssetCategory.company_id.is_(None),
                    AssetCategory.company_id == current_user.company_id,
                ),
            )
        )
        parent = parent_res.scalars().unique().one_or_none()
        if parent is None:
            raise HTTPException(status_code=400, detail="Invalid parent_id")
        # The tree is deliberately category -> subcategory only: deeper nesting
        # makes the statutory grouping in the Schedule III note ambiguous.
        if parent.parent_id is not None:
            raise HTTPException(
                status_code=400,
                detail="Categories are two level only — a subcategory cannot have children",
            )

    if body.default_it_block_id is not None:
        block_res = await db.execute(
            select(ItAssetBlock.id).where(
                ItAssetBlock.id == body.default_it_block_id,
                or_(
                    ItAssetBlock.company_id.is_(None),
                    ItAssetBlock.company_id == current_user.company_id,
                ),
            )
        )
        if block_res.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Invalid default_it_block_id")

    cat = AssetCategory(company_id=current_user.company_id, **body.model_dump())
    db.add(cat)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A category with this name already exists under that parent"
        )
    # Re-select so the joined it_block is loaded for the flattened response.
    result = await db.execute(select(AssetCategory).where(AssetCategory.id == cat.id))
    return result.scalars().unique().one()


@router.patch("/categories/{category_id}", response_model=AssetCategoryResponse)
async def update_category(
    category_id: uuid.UUID, body: AssetCategoryUpdate, current_user: CurrentAdmin, db: Db
):
    cat = await _load_category_for_write(category_id, current_user.company_id, db)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(cat, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A category with this name already exists under that parent"
        )
    result = await db.execute(select(AssetCategory).where(AssetCategory.id == cat.id))
    return result.scalars().unique().one()


# === Suppliers ===

@router.get("/suppliers", response_model=List[SupplierResponse])
async def list_suppliers(current_user: CurrentReader, db: Db, include_inactive: bool = False):
    query = select(Supplier).where(Supplier.company_id == current_user.company_id)
    if not include_inactive:
        query = query.where(Supplier.is_active.is_(True))
    result = await db.execute(query.order_by(Supplier.name))
    return result.scalars().all()


@router.post("/suppliers", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier(body: SupplierCreate, current_user: CurrentAdmin, db: Db):
    data = body.model_dump()
    supplier = Supplier(
        company_id=current_user.company_id,
        state_code=_state_code_from_gstin(data.get("gstin")),
        **data,
    )
    db.add(supplier)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A supplier with this code already exists")
    await db.refresh(supplier)
    return supplier


@router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: uuid.UUID, body: SupplierUpdate, current_user: CurrentAdmin, db: Db
):
    result = await db.execute(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.company_id == current_user.company_id
        )
    )
    supplier = result.scalar_one_or_none()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")

    update = body.model_dump(exclude_unset=True)
    for key, value in update.items():
        setattr(supplier, key, value)
    if "gstin" in update:
        supplier.state_code = _state_code_from_gstin(update["gstin"])
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A supplier with this code already exists")
    await db.refresh(supplier)
    return supplier


# === Lookups ===

@router.get("/lookups", response_model=List[AssetLookupResponse])
async def list_lookups(
    current_user: CurrentReader,
    db: Db,
    kind: Optional[AssetLookupKind] = None,
    include_inactive: bool = False,
):
    query = select(AssetLookup).where(AssetLookup.company_id == current_user.company_id)
    if kind is not None:
        query = query.where(AssetLookup.kind == kind)
    if not include_inactive:
        query = query.where(AssetLookup.is_active.is_(True))
    result = await db.execute(query.order_by(AssetLookup.kind, AssetLookup.display_order, AssetLookup.name))
    return result.scalars().all()


@router.post("/lookups", response_model=AssetLookupResponse, status_code=status.HTTP_201_CREATED)
async def create_lookup(body: AssetLookupCreate, current_user: CurrentAdmin, db: Db):
    if body.parent_id is not None:
        parent_res = await db.execute(
            select(AssetLookup).where(
                AssetLookup.id == body.parent_id,
                AssetLookup.company_id == current_user.company_id,
            )
        )
        parent = parent_res.scalar_one_or_none()
        if parent is None:
            raise HTTPException(status_code=400, detail="Invalid parent_id")
        if parent.kind != body.kind:
            raise HTTPException(
                status_code=400, detail="A lookup's parent must be of the same kind"
            )

    data = body.model_dump()
    lookup = AssetLookup(
        company_id=current_user.company_id,
        state_code=_state_code_from_gstin(data.get("gstin")),
        **data,
    )
    db.add(lookup)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A value with this name already exists for that kind"
        )
    await db.refresh(lookup)
    return lookup


@router.patch("/lookups/{lookup_id}", response_model=AssetLookupResponse)
async def update_lookup(
    lookup_id: uuid.UUID, body: AssetLookupUpdate, current_user: CurrentAdmin, db: Db
):
    result = await db.execute(
        select(AssetLookup).where(
            AssetLookup.id == lookup_id, AssetLookup.company_id == current_user.company_id
        )
    )
    lookup = result.scalar_one_or_none()
    if lookup is None:
        raise HTTPException(status_code=404, detail="Lookup not found")

    update = body.model_dump(exclude_unset=True)
    for key, value in update.items():
        setattr(lookup, key, value)
    if "gstin" in update:
        lookup.state_code = _state_code_from_gstin(update["gstin"])
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A value with this name already exists for that kind"
        )
    await db.refresh(lookup)
    return lookup
