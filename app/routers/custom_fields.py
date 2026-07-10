import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_company_user, require_admin
from app.models.company import CompanyUser
from app.models.custom_fields import CustomFieldDefinition, CustomFieldModule
from app.schemas.custom_fields import CustomFieldCreate, CustomFieldUpdate, CustomFieldResponse

router = APIRouter(prefix="/api/v1/custom-fields", tags=["custom-fields"])

@router.get("/{module}", response_model=List[CustomFieldResponse])
async def list_custom_fields(
    module: CustomFieldModule,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.company_id == current_user.company_id,
            CustomFieldDefinition.module == module,
            CustomFieldDefinition.is_active == True
        )
        .order_by(CustomFieldDefinition.display_order)
    )
    return result.scalars().all()

@router.post("/{module}", response_model=CustomFieldResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_field(
    module: CustomFieldModule,
    body: CustomFieldCreate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # Check key uniqueness for module/company
    existing = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.company_id == current_user.company_id,
            CustomFieldDefinition.module == module,
            CustomFieldDefinition.field_key == body.field_key
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Field key already exists for this module")
        
    field = CustomFieldDefinition(
        company_id=current_user.company_id,
        module=module,
        field_name=body.field_name,
        field_key=body.field_key,
        field_type=body.field_type,
        is_required=body.is_required,
        dropdown_options=body.dropdown_options,
        display_order=body.display_order
    )
    db.add(field)
    await db.commit()
    await db.refresh(field)
    return field

@router.patch("/{module}/{field_id}", response_model=CustomFieldResponse)
async def update_custom_field(
    module: CustomFieldModule,
    field_id: uuid.UUID,
    body: CustomFieldUpdate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.id == field_id,
            CustomFieldDefinition.company_id == current_user.company_id,
            CustomFieldDefinition.module == module
        )
    )
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Custom field not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(field, key, value)

    await db.commit()
    await db.refresh(field)
    return field

@router.patch("/{module}/{field_id}/deactivate", response_model=CustomFieldResponse)
async def deactivate_custom_field(
    module: CustomFieldModule,
    field_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.id == field_id,
            CustomFieldDefinition.company_id == current_user.company_id,
            CustomFieldDefinition.module == module
        )
    )
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Custom field not found")

    field.is_active = False
    await db.commit()
    await db.refresh(field)
    return field

@router.patch("/{module}/{field_id}/reactivate", response_model=CustomFieldResponse)
async def reactivate_custom_field(
    module: CustomFieldModule,
    field_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.id == field_id,
            CustomFieldDefinition.company_id == current_user.company_id,
            CustomFieldDefinition.module == module
        )
    )
    field = result.scalar_one_or_none()
    if not field:
        raise HTTPException(status_code=404, detail="Custom field not found")

    field.is_active = True
    await db.commit()
    await db.refresh(field)
    return field
