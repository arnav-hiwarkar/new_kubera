import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_company_user, require_admin, get_visible_user_ids, require_manager_or_admin
from app.models.company import CompanyUser, UserRole
from app.models.kra import KRAItem, KRAStatus
from app.schemas.kra import KRACreate, KRAUpdate, KRAResponse

router = APIRouter(prefix="/api/v1/kra", tags=["kra"])

@router.get("", response_model=List[KRAResponse])
async def list_kras(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cycle: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None
):
    query = select(KRAItem).where(KRAItem.company_id == current_user.company_id)
    if cycle:
        query = query.where(KRAItem.cycle == cycle)
    
    visible_ids = await get_visible_user_ids(current_user, db)
    
    if user_id:
        if visible_ids is not None and user_id not in visible_ids:
            raise HTTPException(status_code=403, detail="Not authorized to view this user's KRAs")
        query = query.where(KRAItem.user_id == user_id)
    elif visible_ids is not None:
        query = query.where(KRAItem.user_id.in_(visible_ids))
        
    result = await db.execute(query.order_by(KRAItem.created_at.desc()))
    return result.scalars().all()

@router.post("", response_model=KRAResponse, status_code=status.HTTP_201_CREATED)
async def create_kra(
    body: KRACreate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    target_user_id = body.user_id or current_user.id
    
    if target_user_id != current_user.id:
        visible_ids = await get_visible_user_ids(current_user, db)
        if visible_ids is not None and target_user_id not in visible_ids:
            raise HTTPException(status_code=403, detail="Not authorized to assign KRAs to this user")
            
    result = await db.execute(select(CompanyUser).where(CompanyUser.id == target_user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    kra = KRAItem(
        company_id=current_user.company_id,
        title=body.title,
        description=body.description,
        weightage=body.weightage,
        target_metric=body.target_metric,
        cycle=body.cycle,
        user_id=target_user_id,
        manager_id=target_user.manager_id
    )
    db.add(kra)
    await db.commit()
    await db.refresh(kra)
    return kra

@router.get("/{kra_id}", response_model=KRAResponse)
async def get_kra(
    kra_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(KRAItem).where(
            KRAItem.id == kra_id, 
            KRAItem.company_id == current_user.company_id
        )
    )
    kra = result.scalar_one_or_none()
    if not kra:
        raise HTTPException(status_code=404, detail="KRA not found")

    visible_ids = await get_visible_user_ids(current_user, db)
    if visible_ids is not None and kra.user_id not in visible_ids:
        raise HTTPException(status_code=403, detail="Not authorized to view this KRA")
        
    return kra

@router.patch("/{kra_id}", response_model=KRAResponse)
async def update_kra(
    kra_id: uuid.UUID,
    body: KRAUpdate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(KRAItem).where(
            KRAItem.id == kra_id, 
            KRAItem.company_id == current_user.company_id
        )
    )
    kra = result.scalar_one_or_none()
    if not kra:
        raise HTTPException(status_code=404, detail="KRA not found")

    is_owner = kra.user_id == current_user.id
    is_manager = kra.manager_id == current_user.id
    is_admin = current_user.role == UserRole.admin

    if not (is_owner or is_manager or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized to update this KRA")

    update_data = body.model_dump(exclude_unset=True)
    
    if 'manager_rating' in update_data or 'manager_comment' in update_data or 'rejection_reason' in update_data:
        if not (is_manager or is_admin):
            raise HTTPException(status_code=403, detail="Only manager or admin can provide manager ratings")
            
    if 'employee_self_rating' in update_data or 'employee_comment' in update_data:
        if not (is_owner or is_admin):
            raise HTTPException(status_code=403, detail="Only owner can provide self rating")
            
    if 'status' in update_data:
        new_status = update_data['status']
        if new_status in [KRAStatus.approved, KRAStatus.rejected, KRAStatus.completed]:
            if not (is_manager or is_admin):
                raise HTTPException(status_code=403, detail="Only manager or admin can approve/reject/complete")
        if new_status == KRAStatus.review_submitted:
            if not (is_owner or is_admin):
                raise HTTPException(status_code=403, detail="Only owner can submit review")

    for key, value in update_data.items():
        setattr(kra, key, value)

    await db.commit()
    await db.refresh(kra)
    return kra
