import uuid
import json
from typing import Annotated, List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_company_user, require_admin, get_visible_user_ids
from app.models.company import CompanyUser
from app.models.sales import SalesRecord, SalesStatus
from app.schemas.sales import SalesRecordCreate, SalesRecordUpdate, SalesRecordResponse
from app.models.custom_fields import CustomFieldModule
from app.services.custom_field_validator import validate_custom_fields
from app.services.import_service import parse_and_import, ColumnMapping, ImportResult
from app.services.export_service import generate_xlsx, ExportColumn

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])

@router.get("", response_model=List[SalesRecordResponse])
async def list_sales(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Optional[SalesStatus] = None
):
    query = select(SalesRecord).where(SalesRecord.company_id == current_user.company_id)
    if status:
        query = query.where(SalesRecord.status == status)
    
    visible_ids = await get_visible_user_ids(current_user, db)
    if visible_ids is not None:
        query = query.where(SalesRecord.user_id.in_(visible_ids))
        
    result = await db.execute(query.order_by(SalesRecord.created_at.desc()))
    return result.scalars().all()

@router.get("/aggregate")
async def aggregate_sales(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    query = select(SalesRecord.status, func.sum(SalesRecord.amount).label("total_amount"), func.count(SalesRecord.id).label("count"))\
            .where(SalesRecord.company_id == current_user.company_id)
            
    visible_ids = await get_visible_user_ids(current_user, db)
    if visible_ids is not None:
        query = query.where(SalesRecord.user_id.in_(visible_ids))
        
    query = query.group_by(SalesRecord.status)
    result = await db.execute(query)
    
    data = result.all()
    return [{"status": r.status, "total_amount": float(r.total_amount) if r.total_amount else 0.0, "count": r.count} for r in data]

@router.post("", response_model=SalesRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_sales_record(
    body: SalesRecordCreate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    if body.custom_fields:
        errors = await validate_custom_fields(body.custom_fields, current_user.company_id, CustomFieldModule.sales_tracking, db)
        if errors:
            raise HTTPException(status_code=400, detail={"custom_field_errors": errors})

    user_id = body.user_id or current_user.id
    if user_id != current_user.id:
        visible_ids = await get_visible_user_ids(current_user, db)
        if visible_ids is not None and user_id not in visible_ids:
            raise HTTPException(status_code=403, detail="Not authorized to attribute sales to this user")

    sales = SalesRecord(
        company_id=current_user.company_id,
        client_name=body.client_name,
        product_service=body.product_service,
        amount=body.amount,
        status=body.status,
        closing_date=body.closing_date,
        user_id=user_id,
        custom_fields=body.custom_fields
    )
    db.add(sales)
    await db.commit()
    await db.refresh(sales)
    return sales

@router.get("/{sales_id}", response_model=SalesRecordResponse)
async def get_sales_record(
    sales_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(SalesRecord).where(
            SalesRecord.id == sales_id, 
            SalesRecord.company_id == current_user.company_id
        )
    )
    sales = result.scalar_one_or_none()
    if not sales:
        raise HTTPException(status_code=404, detail="Sales record not found")

    visible_ids = await get_visible_user_ids(current_user, db)
    if visible_ids is not None and sales.user_id not in visible_ids:
        raise HTTPException(status_code=403, detail="Not authorized to view this sales record")
        
    return sales

@router.patch("/{sales_id}", response_model=SalesRecordResponse)
async def update_sales_record(
    sales_id: uuid.UUID,
    body: SalesRecordUpdate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(SalesRecord).where(
            SalesRecord.id == sales_id, 
            SalesRecord.company_id == current_user.company_id
        )
    )
    sales = result.scalar_one_or_none()
    if not sales:
        raise HTTPException(status_code=404, detail="Sales record not found")

    visible_ids = await get_visible_user_ids(current_user, db)
    if visible_ids is not None and sales.user_id not in visible_ids:
        raise HTTPException(status_code=403, detail="Not authorized to update this sales record")

    update_data = body.model_dump(exclude_unset=True)

    if 'user_id' in update_data and update_data['user_id'] != sales.user_id:
        if visible_ids is not None and update_data['user_id'] not in visible_ids:
            raise HTTPException(status_code=403, detail="Not authorized to attribute sales to this user")

    if 'custom_fields' in update_data:
        new_custom = sales.custom_fields.copy() if sales.custom_fields else {}
        new_custom.update(update_data['custom_fields'])
        
        errors = await validate_custom_fields(new_custom, current_user.company_id, CustomFieldModule.sales_tracking, db)
        if errors:
            raise HTTPException(status_code=400, detail={"custom_field_errors": errors})
        update_data['custom_fields'] = new_custom

    for key, value in update_data.items():
        setattr(sales, key, value)

    await db.commit()
    await db.refresh(sales)
    return sales

@router.post("/import", response_model=ImportResult)
async def import_sales(
    file: UploadFile = File(...),
    mappings: str = Form(...),
    current_user: CompanyUser = Depends(get_current_company_user),
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
            CustomFieldDefinition.module == CustomFieldModule.sales_tracking,
            CustomFieldDefinition.is_active == True
        )
    )
    custom_defs = result.scalars().all()

    def row_factory(base_data, custom_data):
        user_id = base_data.pop('user_id', current_user.id)
        return SalesRecord(
            company_id=current_user.company_id,
            user_id=user_id,
            custom_fields=custom_data,
            **base_data
        )

    base_validators = {
        "client_name": str,
        "product_service": str,
        "amount": float,
        "status": SalesStatus,
        "user_id": uuid.UUID
    }

    res = await parse_and_import(
        file,
        column_mappings,
        base_validators,
        custom_defs,
        row_factory,
        db,
        current_user.company_id,
        CustomFieldModule.sales_tracking
    )
    return res

@router.get("/export/excel")
async def export_sales(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    query = select(SalesRecord).where(SalesRecord.company_id == current_user.company_id).order_by(SalesRecord.created_at.desc())
    visible_ids = await get_visible_user_ids(current_user, db)
    if visible_ids is not None:
        query = query.where(SalesRecord.user_id.in_(visible_ids))
        
    result = await db.execute(query)
    sales = result.scalars().all()
    
    columns = [
        ExportColumn("Client Name", "client_name"),
        ExportColumn("Product/Service", "product_service"),
        ExportColumn("Amount", "amount"),
        ExportColumn("Status", "status", lambda x: x.value),
    ]
    
    excel_file = generate_xlsx(sales, columns, "Sales")
    return Response(
        content=excel_file.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sales.xlsx"'}
    )
