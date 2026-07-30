"""Fixed asset register — asset units and lifecycle transitions.

Permission model (decision: split, with segregation of duties):
  * read    — anyone with the `assets` module sees the WHOLE register. It is a
              finance artifact: gross block and NBV totals have to tie, so a
              manager seeing only their reports' assets would be misleading.
  * create / edit drafts — anyone with the module.
  * approve -> capitalized — admin or manager, and never your own asset unless
              you are admin.
  * edit after capitalization — admin only, and cost is locked.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_company_user, require_admin, require_assets_module
from app.database import get_db
from app.models.asset_masters import AssetCategory
from app.models.assets import (
    ACQUISITION_DOC_ROLES,
    Asset,
    AssetAcquisition,
    AssetCondition,
    AssetDocument,
    AssetLifecycleStatus,
    AssetOperationalStatus,
)
from app.models.company import CompanyUser, UserRole
from app.models.custom_fields import CustomFieldModule
from app.models.docvault import Document, DocumentVersion
from app.schemas.assets import (
    AssetDetailResponse,
    AssetDocumentResponse,
    AssetQuickAddRequest,
    AssetQuickAddResponse,
    AssetResponse,
    AssetSibling,
    AssetUpdate,
    BulkSerialRequest,
    CostPreviewRequest,
    CostPreviewResponse,
    TransitionRequest,
    TransitionResponse,
    ValidationIssueResponse,
)
from app.services.activity import log_activity
from app.services.asset_costing import AcquisitionCostInput, compute_acquisition_cost
from app.services.asset_register import (
    apply_category_defaults,
    explode_acquisition,
    recompute_acquisition_costs,
    refresh_derived_asset_fields,
    resolve_place_of_supply,
)
from app.services.asset_tags import code_is_taken
from app.services.asset_validation import (
    TAB_ACQUISITION,
    TAB_ASSIGNMENT,
    TAB_DEPRECIATION,
    TAB_DOCUMENTS,
    TAB_IDENTITY,
    TAB_TAX,
    validate_transition,
)
from app.services.custom_field_validator import validate_custom_fields
from app.services.export_service import ExportColumn, generate_xlsx

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

Reader = Annotated[CompanyUser, Depends(require_assets_module)]
Admin = Annotated[CompanyUser, Depends(require_admin)]
Db = Annotated[AsyncSession, Depends(get_db)]

ALL_TABS = (TAB_IDENTITY, TAB_ACQUISITION, TAB_TAX, TAB_DEPRECIATION, TAB_ASSIGNMENT, TAB_DOCUMENTS)

# Fields that may still be edited once an asset is capitalized. Cost, dates and
# depreciation inputs are deliberately absent: changing those after the asset is on
# the books has to go through an explicit cost adjustment (P2) so the depreciation
# already charged stays explainable.
POST_CAPITALIZATION_EDITABLE = frozenset(
    {
        "description",
        "operational_status",
        "condition",
        "branch_id",
        "cost_centre_id",
        "department_id",
        "location_id",
        "custodian_id",
        "custodian_name",
        "custodian_employee_code",
        "manufacturer_contact",
        "manufacturer_serial_number",
        "registration_number",
        "engine_number",
        "chassis_number",
        "imei",
        "mac_address",
        "technical_specs",
        "remarks",
        "parent_asset_id",
        "custom_fields",
        "warranty_start_date",
        "warranty_months",
    }
)


def _asset_query() -> Select:
    return select(Asset).options(
        selectinload(Asset.acquisition), selectinload(Asset.category)
    )


async def _load_asset(asset_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession) -> Asset:
    result = await db.execute(
        _asset_query().where(Asset.id == asset_id, Asset.company_id == company_id)
    )
    asset = result.scalars().unique().one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


async def _present_doc_roles(db: AsyncSession, asset: Asset) -> set:
    """Roles attached to this unit plus roles attached to its acquisition — an
    invoice lives on the acquisition and counts for every unit under it."""
    conditions = [AssetDocument.asset_id == asset.id]
    if asset.acquisition_id is not None:
        conditions.append(AssetDocument.acquisition_id == asset.acquisition_id)
    rows = await db.execute(select(AssetDocument.doc_role).where(or_(*conditions)))
    return set(rows.scalars().all())


async def _category_of(db: AsyncSession, asset: Asset) -> Optional[AssetCategory]:
    if asset.category_id is None:
        return None
    result = await db.execute(select(AssetCategory).where(AssetCategory.id == asset.category_id))
    return result.scalars().unique().one_or_none()


def _next_target(asset: Asset) -> AssetLifecycleStatus:
    """The transition the detail page's checklist should be measured against."""
    if asset.lifecycle_status == AssetLifecycleStatus.draft:
        return AssetLifecycleStatus.ready
    if asset.lifecycle_status == AssetLifecycleStatus.ready:
        return AssetLifecycleStatus.capitalized
    return asset.lifecycle_status


def _completeness_by_tab(issues) -> dict:
    """Rough per-tab completeness so each tab header can show a pill. 100 means
    nothing on that tab is blocking the next transition."""
    counts = {tab: 0 for tab in ALL_TABS}
    for issue in issues:
        if issue.tab in counts:
            counts[issue.tab] += 1
    # Denominator is a fixed nominal field count per tab; precision here matters
    # less than "this tab still needs attention".
    nominal = {
        TAB_IDENTITY: 5,
        TAB_ACQUISITION: 6,
        TAB_TAX: 3,
        TAB_DEPRECIATION: 8,
        TAB_ASSIGNMENT: 6,
        TAB_DOCUMENTS: 2,
    }
    return {
        tab: max(0, round(100 * (nominal[tab] - counts[tab]) / nominal[tab]))
        for tab in ALL_TABS
    }


# ==========================================================================
# Literal paths first: FastAPI matches in declaration order, and /{asset_id}
# would otherwise swallow /quick-add and /export/excel as malformed UUIDs.
# ==========================================================================

@router.post("/quick-add", response_model=AssetQuickAddResponse, status_code=status.HTTP_201_CREATED)
async def quick_add(body: AssetQuickAddRequest, current_user: Reader, db: Db):
    """Create a draft acquisition and explode it into `quantity` asset units.

    Six fields in, a saved draft out. Everything else is enrichment on the detail
    page — nothing here blocks on statutory data the user may not have yet.
    """
    category = (
        await db.execute(
            select(AssetCategory).where(
                AssetCategory.id == body.category_id,
                or_(
                    AssetCategory.company_id.is_(None),
                    AssetCategory.company_id == current_user.company_id,
                ),
            )
        )
    ).scalars().unique().one_or_none()
    if category is None:
        raise HTTPException(status_code=400, detail="Invalid category_id")

    acquisition = AssetAcquisition(
        company_id=current_user.company_id,
        supplier_id=body.supplier_id,
        purchase_date=body.purchase_date,
        quantity=body.quantity,
        unit_basic_price=body.unit_basic_price,
        branch_id=body.branch_id,
        itc_treatment=category.default_itc_treatment,
        created_by=current_user.id,
    )
    db.add(acquisition)
    await db.flush()

    units = await explode_acquisition(
        db,
        acquisition,
        asset_name=body.asset_name.strip(),
        category_id=body.category_id,
        created_by=current_user.id,
        branch_id=body.branch_id,
    )

    await log_activity(
        db,
        current_user.company_id,
        current_user.id,
        "asset.created",
        "asset_acquisition",
        acquisition.id,
        {"quantity": body.quantity, "asset_name": body.asset_name},
    )
    await db.commit()

    return AssetQuickAddResponse(
        acquisition_id=acquisition.id,
        asset_ids=[u.id for u in units],
        first_asset_id=units[0].id,
        quantity=len(units),
    )


@router.post("/cost-preview", response_model=CostPreviewResponse)
async def cost_preview(body: CostPreviewRequest, current_user: Reader, db: Db):
    """Server-authoritative costing for the live form, so the numbers the user sees
    while typing are the numbers that will be stored."""
    supplier_state = None
    if body.supplier_id is not None:
        from app.models.asset_masters import Supplier

        supplier = (
            await db.execute(
                select(Supplier).where(
                    Supplier.id == body.supplier_id,
                    Supplier.company_id == current_user.company_id,
                )
            )
        ).scalar_one_or_none()
        if supplier is not None:
            supplier_state = supplier.state_code

    pos = await resolve_place_of_supply(db, current_user.company_id, body.branch_id)

    try:
        breakdown = compute_acquisition_cost(
            AcquisitionCostInput(
                quantity=body.quantity,
                unit_basic_price=body.unit_basic_price,
                discount_type=body.discount_type,
                discount_value=body.discount_value,
                gst_rate=body.gst_rate,
                supplier_state_code=supplier_state,
                place_of_supply_state_code=pos,
                itc_treatment=body.itc_treatment,
                itc_eligible_pct=body.itc_eligible_pct,
                freight_cost=body.freight_cost,
                installation_cost=body.installation_cost,
                other_capitalizable_cost=body.other_capitalizable_cost,
                cgst_amount_override=body.cgst_amount_override,
                sgst_amount_override=body.sgst_amount_override,
                igst_amount_override=body.igst_amount_override,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CostPreviewResponse(
        gross_basic_price=breakdown.gross_basic_price,
        discount_amount=breakdown.discount_amount,
        net_basic_price=breakdown.net_basic_price,
        gst_split_basis=breakdown.gst_split_basis,
        cgst_amount=breakdown.cgst_amount,
        sgst_amount=breakdown.sgst_amount,
        igst_amount=breakdown.igst_amount,
        total_gst=breakdown.total_gst,
        recoverable_gst=breakdown.recoverable_gst,
        capitalizable_gst=breakdown.capitalizable_gst,
        landed_cost=breakdown.landed_cost,
        total_acquisition_outlay=breakdown.total_acquisition_outlay,
        per_unit_cost=breakdown.per_unit_cost,
    )


@router.get("/export/excel")
async def export_assets(current_user: Reader, db: Db):
    result = await db.execute(
        _asset_query()
        .where(Asset.company_id == current_user.company_id)
        .order_by(Asset.created_at.desc())
    )
    assets = result.scalars().unique().all()

    columns = [
        ExportColumn("Asset code", "asset_code"),
        ExportColumn("Asset name", "asset_name"),
        ExportColumn("Serial number", "manufacturer_serial_number"),
        ExportColumn("Category", "category", lambda c: c.name if c else None),
        ExportColumn("Lifecycle", "lifecycle_status", lambda s: s.value if s else None),
        ExportColumn("Condition", "condition", lambda s: s.value if s else None),
        ExportColumn("Capitalization date", "capitalization_date"),
        ExportColumn("Original cost", "original_cost", lambda v: float(v) if v is not None else None),
        ExportColumn("Useful life (months)", "useful_life_months"),
        ExportColumn("Method", "dep_method", lambda m: m.value if m else None),
        ExportColumn("IT block", "it_block", lambda b: b.code if b else None),
        ExportColumn("IT rate", "it_dep_rate", lambda v: float(v) if v is not None else None),
    ]
    excel_file = generate_xlsx(assets, columns, "Fixed assets")
    return Response(
        content=excel_file.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="fixed_assets.xlsx"'},
    )


@router.get("", response_model=List[AssetResponse])
async def list_assets(
    current_user: Reader,
    db: Db,
    lifecycle_status: Optional[AssetLifecycleStatus] = None,
    operational_status: Optional[AssetOperationalStatus] = None,
    condition: Optional[AssetCondition] = None,
    category_id: Optional[uuid.UUID] = None,
    location_id: Optional[uuid.UUID] = None,
    branch_id: Optional[uuid.UUID] = None,
    custodian_id: Optional[uuid.UUID] = None,
    acquisition_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
):
    """The register, whole. Scoped by company only — see the module docstring for
    why this is not narrowed by custodian."""
    query = _asset_query().where(Asset.company_id == current_user.company_id)
    for column, value in (
        (Asset.lifecycle_status, lifecycle_status),
        (Asset.operational_status, operational_status),
        (Asset.condition, condition),
        (Asset.category_id, category_id),
        (Asset.location_id, location_id),
        (Asset.branch_id, branch_id),
        (Asset.custodian_id, custodian_id),
        (Asset.acquisition_id, acquisition_id),
    ):
        if value is not None:
            query = query.where(column == value)
    if search:
        like = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Asset.asset_name).like(like),
                func.lower(Asset.asset_code).like(like),
                func.lower(Asset.manufacturer_serial_number).like(like),
            )
        )
    result = await db.execute(query.order_by(Asset.created_at.desc(), Asset.unit_index))
    return result.scalars().unique().all()


@router.get("/{asset_id}", response_model=AssetDetailResponse)
async def get_asset(asset_id: uuid.UUID, current_user: Reader, db: Db):
    """Everything the tabbed detail page needs in one round trip, including the
    checklist of what is blocking the next transition."""
    asset = await _load_asset(asset_id, current_user.company_id, db)
    category = await _category_of(db, asset)
    roles = await _present_doc_roles(db, asset)

    issues = validate_transition(
        asset, asset.acquisition, _next_target(asset), present_doc_roles=roles, category=category
    )

    siblings = []
    if asset.acquisition_id is not None:
        sib_rows = await db.execute(
            select(Asset)
            .where(Asset.acquisition_id == asset.acquisition_id)
            .order_by(Asset.unit_index)
        )
        siblings = [AssetSibling.model_validate(s) for s in sib_rows.scalars().unique().all()]

    documents = await _list_documents(db, asset)

    return AssetDetailResponse(
        asset=AssetResponse.model_validate(asset),
        acquisition=asset.acquisition,
        siblings=siblings,
        documents=documents,
        applicable_field_groups=list(category.applicable_field_groups or []) if category else [],
        blocking_issues=[ValidationIssueResponse(**i.as_dict()) for i in issues],
        completeness_by_tab=_completeness_by_tab(issues),
    )


async def _list_documents(db: AsyncSession, asset: Asset) -> List[AssetDocumentResponse]:
    conditions = [AssetDocument.asset_id == asset.id]
    if asset.acquisition_id is not None:
        conditions.append(AssetDocument.acquisition_id == asset.acquisition_id)
    rows = await db.execute(
        select(AssetDocument, Document, DocumentVersion)
        .join(Document, Document.id == AssetDocument.document_id)
        .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
        .where(or_(*conditions))
        .order_by(AssetDocument.created_at)
    )
    out = []
    for link, doc, version in rows.all():
        payload = AssetDocumentResponse.model_validate(link)
        payload.title = doc.title
        if version is not None:
            payload.original_filename = version.original_filename
            payload.mime_type = version.mime_type
            payload.size_bytes = version.size_bytes
        out.append(payload)
    return out


@router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset(asset_id: uuid.UUID, body: AssetUpdate, current_user: Reader, db: Db):
    asset = await _load_asset(asset_id, current_user.company_id, db)
    update = body.model_dump(exclude_unset=True)

    is_admin = current_user.role == UserRole.admin
    if asset.lifecycle_status in (AssetLifecycleStatus.capitalized, AssetLifecycleStatus.disposed):
        if not is_admin:
            raise HTTPException(
                status_code=403, detail="Only an admin can edit a capitalized asset"
            )
        locked = set(update) - POST_CAPITALIZATION_EDITABLE
        if locked:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "These fields are locked once the asset is capitalized. Record a cost "
                        "adjustment or transfer instead of editing them."
                    ),
                    "locked_fields": sorted(locked),
                },
            )

    if "asset_code" in update and update["asset_code"]:
        if asset.lifecycle_status != AssetLifecycleStatus.draft:
            raise HTTPException(
                status_code=409,
                detail="Asset code can only be changed while the asset is a draft",
            )
        code = update["asset_code"].strip()
        if await code_is_taken(db, current_user.company_id, code, exclude_asset_id=asset.id):
            raise HTTPException(status_code=409, detail="This asset code is already in use")
        update["asset_code"] = code

    if "custom_fields" in update:
        merged = dict(asset.custom_fields or {})
        merged.update(update["custom_fields"] or {})
        errors = await validate_custom_fields(
            merged, current_user.company_id, CustomFieldModule.asset_management, db
        )
        if errors:
            raise HTTPException(status_code=400, detail={"custom_field_errors": errors})
        update["custom_fields"] = merged

    category_changed = "category_id" in update and update["category_id"] != asset.category_id

    for key, value in update.items():
        setattr(asset, key, value)

    if category_changed and asset.category_id is not None:
        # Re-derive the statutory defaults, but only for fields the user has not
        # explicitly set — apply_category_defaults never clobbers a value.
        await apply_category_defaults(db, asset, asset.category_id)

    refresh_derived_asset_fields(asset)

    await log_activity(
        db,
        current_user.company_id,
        current_user.id,
        "asset.updated",
        "asset",
        asset.id,
        {"fields": sorted(update.keys())},
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This asset code is already in use")
    await db.refresh(asset)
    return asset


@router.post("/{asset_id}/serials", response_model=List[AssetResponse])
async def assign_serials(asset_id: uuid.UUID, body: BulkSerialRequest, current_user: Reader, db: Db):
    """Fill per-unit serials (and optionally codes) for an exploded batch in one
    call — the grid step that makes a 50-unit explode practical."""
    anchor = await _load_asset(asset_id, current_user.company_id, db)
    if anchor.acquisition_id is None:
        raise HTTPException(status_code=400, detail="Asset has no acquisition batch")

    ids = [a.asset_id for a in body.assignments]
    rows = await db.execute(
        select(Asset).where(
            Asset.id.in_(ids),
            Asset.company_id == current_user.company_id,
            Asset.acquisition_id == anchor.acquisition_id,
        )
    )
    by_id = {a.id: a for a in rows.scalars().unique().all()}
    missing = set(ids) - set(by_id)
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Some assets are not part of this acquisition batch",
        )

    for assignment in body.assignments:
        unit = by_id[assignment.asset_id]
        if assignment.manufacturer_serial_number is not None:
            unit.manufacturer_serial_number = assignment.manufacturer_serial_number.strip() or None
        if assignment.asset_code is not None and assignment.asset_code.strip():
            if unit.lifecycle_status != AssetLifecycleStatus.draft:
                raise HTTPException(
                    status_code=409,
                    detail="Asset code can only be changed while the asset is a draft",
                )
            code = assignment.asset_code.strip()
            if await code_is_taken(db, current_user.company_id, code, exclude_asset_id=unit.id):
                raise HTTPException(
                    status_code=409, detail=f"Asset code {code} is already in use"
                )
            unit.asset_code = code

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate asset code in the batch")
    return list(by_id.values())


async def _units_for_transition(
    asset: Asset, apply_to_siblings: bool, db: AsyncSession
) -> List[Asset]:
    if not apply_to_siblings or asset.acquisition_id is None:
        return [asset]
    rows = await db.execute(
        _asset_query()
        .where(Asset.acquisition_id == asset.acquisition_id, Asset.company_id == asset.company_id)
        .order_by(Asset.unit_index)
    )
    return list(rows.scalars().unique().all())


@router.post("/{asset_id}/submit", response_model=TransitionResponse)
async def submit_asset(
    asset_id: uuid.UUID, body: TransitionRequest, current_user: Reader, db: Db
):
    """draft -> ready. Fails with the full checklist rather than the first error."""
    anchor = await _load_asset(asset_id, current_user.company_id, db)
    units = await _units_for_transition(anchor, body.apply_to_siblings, db)

    updated = []
    now = datetime.now(timezone.utc)
    for unit in units:
        if unit.lifecycle_status != AssetLifecycleStatus.draft:
            if not body.apply_to_siblings:
                raise HTTPException(
                    status_code=409,
                    detail=f"Only a draft can be submitted (this asset is {unit.lifecycle_status.value})",
                )
            continue
        category = await _category_of(db, unit)
        roles = await _present_doc_roles(db, unit)
        issues = validate_transition(
            unit, unit.acquisition, AssetLifecycleStatus.ready, present_doc_roles=roles, category=category
        )
        if issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "This asset is not complete enough to submit",
                    "asset_id": str(unit.id),
                    "asset_code": unit.asset_code,
                    "issues": [i.as_dict() for i in issues],
                },
            )
        unit.lifecycle_status = AssetLifecycleStatus.ready
        unit.submitted_by = current_user.id
        unit.submitted_at = now
        updated.append(unit.id)
        await log_activity(
            db,
            current_user.company_id,
            current_user.id,
            "asset.submitted",
            "asset",
            unit.id,
            {"note": body.note},
        )

    await db.commit()
    return TransitionResponse(updated=updated, lifecycle_status=AssetLifecycleStatus.ready)


@router.post("/{asset_id}/approve", response_model=TransitionResponse)
async def approve_asset(
    asset_id: uuid.UUID,
    body: TransitionRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Db,
):
    """ready -> capitalized. Admin or manager, and never your own asset unless you
    are an admin — an unreviewed capitalized cost enters the depreciation base."""
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=403, detail="Only an admin or manager can approve an asset"
        )
    anchor = await _load_asset(asset_id, current_user.company_id, db)
    units = await _units_for_transition(anchor, body.apply_to_siblings, db)

    updated = []
    now = datetime.now(timezone.utc)
    for unit in units:
        if unit.lifecycle_status != AssetLifecycleStatus.ready:
            if not body.apply_to_siblings:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Only an asset awaiting approval can be capitalized "
                        f"(this asset is {unit.lifecycle_status.value})"
                    ),
                )
            continue
        if current_user.role != UserRole.admin and unit.created_by == current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You cannot approve an asset you created. Ask an admin to approve it.",
            )
        category = await _category_of(db, unit)
        roles = await _present_doc_roles(db, unit)
        issues = validate_transition(
            unit,
            unit.acquisition,
            AssetLifecycleStatus.capitalized,
            present_doc_roles=roles,
            category=category,
        )
        if issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "This asset cannot be capitalized yet",
                    "asset_id": str(unit.id),
                    "asset_code": unit.asset_code,
                    "issues": [i.as_dict() for i in issues],
                },
            )
        unit.lifecycle_status = AssetLifecycleStatus.capitalized
        unit.approved_by = current_user.id
        unit.approved_at = now
        updated.append(unit.id)
        await log_activity(
            db,
            current_user.company_id,
            current_user.id,
            "asset.capitalized",
            "asset",
            unit.id,
            {
                "note": body.note,
                "original_cost": str(unit.original_cost),
                "capitalization_date": str(unit.capitalization_date),
            },
        )

    await db.commit()
    return TransitionResponse(updated=updated, lifecycle_status=AssetLifecycleStatus.capitalized)


@router.post("/{asset_id}/reject", response_model=TransitionResponse)
async def reject_asset(
    asset_id: uuid.UUID,
    body: TransitionRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Db,
):
    """ready -> draft, so the submitter can fix it."""
    if current_user.role not in (UserRole.admin, UserRole.manager):
        raise HTTPException(
            status_code=403, detail="Only an admin or manager can reject an asset"
        )
    anchor = await _load_asset(asset_id, current_user.company_id, db)
    units = await _units_for_transition(anchor, body.apply_to_siblings, db)

    updated = []
    for unit in units:
        if unit.lifecycle_status != AssetLifecycleStatus.ready:
            continue
        unit.lifecycle_status = AssetLifecycleStatus.draft
        unit.submitted_by = None
        unit.submitted_at = None
        updated.append(unit.id)
        await log_activity(
            db,
            current_user.company_id,
            current_user.id,
            "asset.rejected",
            "asset",
            unit.id,
            {"note": body.note},
        )
    if not updated:
        raise HTTPException(status_code=409, detail="No asset awaiting approval")
    await db.commit()
    return TransitionResponse(updated=updated, lifecycle_status=AssetLifecycleStatus.draft)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft_asset(asset_id: uuid.UUID, current_user: Admin, db: Db):
    """Drafts can be deleted outright. A capitalized asset never can — it leaves
    the register through disposal (P2), which is an accounting event with a
    profit-or-loss consequence, not a delete."""
    asset = await _load_asset(asset_id, current_user.company_id, db)
    if asset.lifecycle_status != AssetLifecycleStatus.draft:
        raise HTTPException(
            status_code=409,
            detail="Only a draft can be deleted. Capitalized assets must be disposed of.",
        )
    acquisition_id = asset.acquisition_id
    await db.delete(asset)
    await db.flush()

    # An acquisition with no remaining units is meaningless; clean it up.
    if acquisition_id is not None:
        remaining = (
            await db.execute(
                select(func.count()).select_from(Asset).where(Asset.acquisition_id == acquisition_id)
            )
        ).scalar_one()
        if remaining == 0:
            acq = (
                await db.execute(
                    select(AssetAcquisition).where(AssetAcquisition.id == acquisition_id)
                )
            ).scalar_one_or_none()
            if acq is not None:
                await db.delete(acq)
        else:
            acq = (
                await db.execute(
                    select(AssetAcquisition).where(AssetAcquisition.id == acquisition_id)
                )
            ).scalar_one_or_none()
            if acq is not None:
                acq.quantity = remaining
                await recompute_acquisition_costs(db, acq)

    await log_activity(
        db, current_user.company_id, current_user.id, "asset.deleted", "asset", asset_id, None
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
