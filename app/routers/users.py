import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_company_user, require_admin, require_manager_or_admin, hash_password
from app.models.company import CompanyUser, UserRole
from app.schemas.users import UserCreate, UserUpdate, UserResponse
from app.auth import get_direct_report_ids
from app.services import account_admin

router = APIRouter(prefix="/api/v1/users", tags=["users"])

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    # Only live accounts hold an email (matches the active-email partial unique
    # index) — a soft-deleted user's address is free to reuse.
    existing = await db.execute(
        select(CompanyUser).where(
            func.lower(CompanyUser.email) == body.email.lower(),
            CompanyUser.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    if body.manager_id:
        m_res = await db.execute(
            select(CompanyUser).where(
                CompanyUser.id == body.manager_id,
                CompanyUser.company_id == current_user.company_id,
                CompanyUser.role.in_([UserRole.manager, UserRole.admin])
            )
        )
        if not m_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid manager_id")

    user = CompanyUser(
        company_id=current_user.company_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        manager_id=body.manager_id,
        designation=body.designation,
        department=body.department,
        accessible_modules=body.accessible_modules,
        is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.get("", response_model=List[UserResponse])
async def list_users(
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(CompanyUser).where(CompanyUser.company_id == current_user.company_id))
    return result.scalars().all()

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
):
    return current_user

@router.get("/me/reports", response_model=List[UserResponse])
async def get_my_reports(
    current_user: Annotated[CompanyUser, Depends(require_manager_or_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    report_ids = await get_direct_report_ids(current_user.id, db)
    if not report_ids:
        return []
    result = await db.execute(
        select(CompanyUser).where(CompanyUser.id.in_(report_ids))
    )
    return result.scalars().all()

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.id == user_id, 
            CompanyUser.company_id == current_user.company_id
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.id == user_id, 
            CompanyUser.company_id == current_user.company_id
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.manager_id and body.manager_id != user.manager_id:
        if body.manager_id == user.id:
            raise HTTPException(status_code=400, detail="User cannot be their own manager")
        
        m_res = await db.execute(
            select(CompanyUser).where(
                CompanyUser.id == body.manager_id,
                CompanyUser.company_id == current_user.company_id,
                CompanyUser.role.in_([UserRole.manager, UserRole.admin])
            )
        )
        if not m_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid manager_id")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Soft-delete a user. Admin only, scoped to the caller's company.

    The user's login is disabled and their email is freed for reuse, but the row
    (and full_name) is kept so any file or record they created still shows their
    name. This always succeeds even when the user owns tenant data. You cannot
    delete your own account (which also keeps at least one admin around).
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.id == user_id,
            CompanyUser.company_id == current_user.company_id
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await account_admin.soft_delete_company_user(db, user)
    await db.commit()
    return None


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Reversibly disable a user's login. Keeps the account and email."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.id == user_id,
            CompanyUser.company_id == current_user.company_id
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}/reactivate", response_model=UserResponse)
async def reactivate_user(
    user_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Re-enable a deactivated user. A soft-deleted user cannot be reactivated —
    recreate the account instead (their email is already free to reuse)."""
    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.id == user_id,
            CompanyUser.company_id == current_user.company_id
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.deleted_at is not None:
        raise HTTPException(
            status_code=409,
            detail="This user was deleted and cannot be reactivated. Recreate the account instead.",
        )

    user.is_active = True
    await db.commit()
    await db.refresh(user)
    return user
