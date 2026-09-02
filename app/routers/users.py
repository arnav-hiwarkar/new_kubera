import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.auth import (
    get_current_company_user,
    require_admin,
    require_manager_or_admin,
    hash_password,
    verify_password,
    get_direct_report_ids,
)
from app.encryption import decrypt_company_kek, encrypt_file_data, decrypt_file_data
from app.models.company import CompanyKey, CompanyUser, UserRole
from app.models.activity_log import ActivityLog, ActorType
from app.schemas.users import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserChangePasswordRequest,
)
from app.services import account_admin
from app.services.user_security import validate_password_complexity, detect_image_format
from app.access_modules import normalize_accessible_modules

router = APIRouter(prefix="/api/v1/users", tags=["users"])

MAX_AVATAR_BYTES = 1024 * 1024  # 1 MB
AVATAR_COOLDOWN = timedelta(hours=3)
PASSWORD_COOLDOWN = timedelta(days=30)
AVATAR_EXT_TO_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


async def _company_kek(db: AsyncSession, company_id: uuid.UUID) -> bytes:
    key = (
        await db.execute(select(CompanyKey).where(CompanyKey.company_id == company_id))
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=500, detail="Company encryption key not found")
    return decrypt_company_kek(key.encrypted_kek, key.kek_nonce)


async def _stream_avatar(db: AsyncSession, user: CompanyUser) -> Response:
    if not user.avatar_path or not os.path.exists(user.avatar_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile picture set")

    ext = Path(user.avatar_path).with_suffix("").suffix.lstrip(".")
    mime = AVATAR_EXT_TO_MIME.get(ext, "application/octet-stream")

    blob = Path(user.avatar_path).read_bytes()
    if len(blob) < 12:
        raise HTTPException(status_code=500, detail="Corrupt avatar payload")

    nonce, ciphertext = blob[:12], blob[12:]
    kek = await _company_kek(db, user.company_id)
    data = decrypt_file_data(ciphertext, nonce, kek)

    headers = {
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=3600",
    }
    return Response(content=data, media_type=mime, headers=headers)


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
                CompanyUser.role == UserRole.admin
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
        accessible_modules=normalize_accessible_modules(body.accessible_modules),
        can_change_password=body.can_change_password,
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


@router.post("/me/change-password")
async def change_password(
    body: UserChangePasswordRequest,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Change the authenticated user's password."""
    if not current_user.can_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to change your password",
        )

    if current_user.password_changed_at is not None:
        now = datetime.now(timezone.utc)
        pwd_changed = current_user.password_changed_at
        if pwd_changed.tzinfo is None:
            pwd_changed = pwd_changed.replace(tzinfo=timezone.utc)
        diff = now - pwd_changed
        if diff < PASSWORD_COOLDOWN:
            remaining = PASSWORD_COOLDOWN - diff
            remaining_days = max(1, remaining.days)
            next_allowed = (pwd_changed + PASSWORD_COOLDOWN).strftime("%Y-%m-%d %H:%M UTC")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Password can only be changed once every 30 days. Next change allowed on {next_allowed} (in {remaining_days} days).",
            )

    if not verify_password(body.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if body.new_password != body.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match",
        )

    if body.new_password == body.old_password or verify_password(body.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from your current password",
        )



    current_user.hashed_password = hash_password(body.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)

    db.add(
        ActivityLog(
            company_id=current_user.company_id,
            actor_type=ActorType.company_user,
            actor_id=current_user.id,
            action="user.password_changed",
            entity_type="company_user",
            entity_id=current_user.id,
        )
    )
    await db.commit()
    return {"success": True, "message": "Password changed successfully"}


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Upload/replace user profile picture with 3-hour cooldown and <=1MB validation."""
    if current_user.avatar_updated_at is not None:
        now = datetime.now(timezone.utc)
        avatar_updated = current_user.avatar_updated_at
        if avatar_updated.tzinfo is None:
            avatar_updated = avatar_updated.replace(tzinfo=timezone.utc)
        diff = now - avatar_updated
        if diff < AVATAR_COOLDOWN:
            remaining_mins = max(1, int((AVATAR_COOLDOWN - diff).total_seconds() // 60))
            next_allowed = (avatar_updated + AVATAR_COOLDOWN).strftime("%H:%M UTC")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Profile picture can only be changed once every 3 hours. Next change allowed at {next_allowed} (in {remaining_mins} minutes).",
            )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Avatar must be 1 MB or smaller",
        )

    ext = detect_image_format(data)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Avatar must be a valid JPG, PNG, or WEBP image",
        )

    kek = await _company_kek(db, current_user.company_id)
    ciphertext, nonce = encrypt_file_data(data, kek)

    vault_dir = Path(get_settings().VAULT_STORAGE_PATH) / "users" / str(current_user.id)
    vault_dir.mkdir(parents=True, exist_ok=True)
    storage_path = vault_dir / f"avatar_{uuid.uuid4()}.{ext}.enc"
    storage_path.write_bytes(nonce + ciphertext)

    old_path = current_user.avatar_path
    current_user.avatar_path = str(storage_path)
    current_user.avatar_updated_at = datetime.now(timezone.utc)

    db.add(
        ActivityLog(
            company_id=current_user.company_id,
            actor_type=ActorType.company_user,
            actor_id=current_user.id,
            action="user.avatar_updated",
            entity_type="company_user",
            entity_id=current_user.id,
        )
    )
    await db.commit()
    await db.refresh(current_user)

    if old_path and old_path != str(storage_path) and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except OSError:
            pass

    return current_user


@router.get("/me/avatar")
async def get_my_avatar(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Stream current user decrypted profile picture."""
    return await _stream_avatar(db, current_user)


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


@router.get("/{user_id}/avatar")
async def get_user_avatar(
    user_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Stream another tenant user's decrypted profile picture."""
    result = await db.execute(
        select(CompanyUser).where(
            CompanyUser.id == user_id,
            CompanyUser.company_id == current_user.company_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return await _stream_avatar(db, user)


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
                CompanyUser.role == UserRole.admin
            )
        )
        if not m_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid manager_id")

    update_data = body.model_dump(exclude_unset=True)
    if update_data.get("accessible_modules") is not None:
        update_data["accessible_modules"] = normalize_accessible_modules(
            update_data["accessible_modules"]
        )
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
