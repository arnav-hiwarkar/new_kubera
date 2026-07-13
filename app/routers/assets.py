import uuid
import json
from typing import Annotated, List, Optional
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_company_user, require_admin, get_visible_user_ids
from app.models.company import CompanyUser
from app.models.assets import Asset, AssetCategory, AssetStatus
from app.schemas.assets import AssetCreate, AssetUpdate, AssetResponse
from app.models.custom_fields import CustomFieldModule
from app.services.custom_field_validator import validate_custom_fields
from app.services.import_service import parse_and_import, ColumnMapping, ImportResult
from app.services.export_service import generate_xlsx, ExportColumn

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


def _parse_import_date(value) -> date:
    """Coerce a spreadsheet cell into a date. openpyxl hands back datetime/date
    objects; CSV hands back strings. Accepts ISO plus a few common day-first and
    month-first formats. Raises ValueError on anything unparseable (the importer
    turns that into a per-row error)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date: {value}")

@router.get("", response_model=List[AssetResponse])
async def list_assets(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Optional[AssetCategory] = None,
    status: Optional[AssetStatus] = None
):
    query = select(Asset).where(Asset.company_id == current_user.company_id)
    if category:
        query = query.where(Asset.category == category)
    if status:
        query = query.where(Asset.status == status)
    
    visible_ids = await get_visible_user_ids(current_user, db)
    if visible_ids is not None:
        query = query.where(
            or_(
                Asset.custodian_id.in_(visible_ids),
                Asset.custodian_id == None
            )
        )
        
    result = await db.execute(query.order_by(Asset.created_at.desc()))
    return result.scalars().all()

@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    body: AssetCreate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if body.custom_fields:
        errors = await validate_custom_fields(body.custom_fields, current_user.company_id, CustomFieldModule.asset_management, db)
        if errors:
            raise HTTPException(status_code=400, detail={"custom_field_errors": errors})

    asset = Asset(
        company_id=current_user.company_id,
        **body.model_dump()
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset

@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Asset).where(
            Asset.id == asset_id, 
            Asset.company_id == current_user.company_id
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    visible_ids = await get_visible_user_ids(current_user, db)
    if visible_ids is not None and asset.custodian_id and asset.custodian_id not in visible_ids:
        raise HTTPException(status_code=403, detail="Not authorized to view this asset")
        
    return asset

@router.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: uuid.UUID,
    body: AssetUpdate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Asset).where(
            Asset.id == asset_id, 
            Asset.company_id == current_user.company_id
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    update_data = body.model_dump(exclude_unset=True)

    if 'custom_fields' in update_data:
        new_custom = asset.custom_fields.copy() if asset.custom_fields else {}
        new_custom.update(update_data['custom_fields'])
        
        errors = await validate_custom_fields(new_custom, current_user.company_id, CustomFieldModule.asset_management, db)
        if errors:
            raise HTTPException(status_code=400, detail={"custom_field_errors": errors})
        update_data['custom_fields'] = new_custom

    for key, value in update_data.items():
        setattr(asset, key, value)

    await db.commit()
    await db.refresh(asset)
    return asset

@router.post("/import", response_model=ImportResult)
async def import_assets(
    file: UploadFile = File(...),
    mappings: str = Form(...),
    current_user: CompanyUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    try:
        mappings_data = json.loads(mappings)
        column_mappings = [ColumnMapping(**m) for m in mappings_data]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid mappings JSON")

    from app.models.custom_fields import CustomFieldDefinition
    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.company_id == current_user.company_id,
            CustomFieldDefinition.module == CustomFieldModule.asset_management,
            CustomFieldDefinition.is_active == True
        )
    )
    custom_defs = result.scalars().all()

    def row_factory(base_data, custom_data):
        return Asset(
            company_id=current_user.company_id,
            custom_fields=custom_data,
            **base_data
        )

    base_validators = {
        "asset_name": str,
        "serial_number": str,
        "category": AssetCategory,
        "status": AssetStatus,
        "purchase_date": _parse_import_date,
        "purchase_cost": float,
    }

    res = await parse_and_import(
        file,
        column_mappings,
        base_validators,
        custom_defs,
        row_factory,
        db,
        current_user.company_id,
        CustomFieldModule.asset_management
    )
    return res

@router.get("/export/excel")
async def export_assets(
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Asset).where(Asset.company_id == current_user.company_id).order_by(Asset.created_at.desc())
    )
    assets = result.scalars().all()
    
    columns = [
        ExportColumn("Asset Name", "asset_name"),
        ExportColumn("Serial Number", "serial_number"),
        ExportColumn("Category", "category", lambda x: x.value),
        ExportColumn("Status", "status", lambda x: x.value),
        ExportColumn("Purchase Cost", "purchase_cost"),
    ]
    
    excel_file = generate_xlsx(assets, columns, "Assets")
    return Response(
        content=excel_file.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="assets.xlsx"'}
    )
