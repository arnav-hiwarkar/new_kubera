"""Company profile: view/edit tenant details + logo. Onboarding + settings."""
import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_company_user, require_admin
from app.config import get_settings
from app.database import get_db
from app.encryption import decrypt_company_kek, encrypt_file_data, decrypt_file_data
from app.models.activity_log import ActivityLog, ActorType
from app.models.company import Company, CompanyKey, CompanyUser
from app.schemas.company import (
    CompanyProfileOut,
    CompanyProfileUpdate,
    REQUIRED_PROFILE_FIELDS,
)

router = APIRouter(prefix="/api/v1/company", tags=["company"])

MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
# Accepted logo types -> file extension used on disk.
LOGO_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/svg+xml": "svg",
}
EXT_TO_MIME = {v: k for k, v in LOGO_TYPES.items()}


async def _company_kek(db: AsyncSession, company_id: uuid.UUID) -> bytes:
    key = (
        await db.execute(select(CompanyKey).where(CompanyKey.company_id == company_id))
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=500, detail="Company encryption key not found")
    return decrypt_company_kek(key.encrypted_kek, key.kek_nonce)


def _profile_is_complete(company: Company) -> bool:
    return all(getattr(company, f) for f in REQUIRED_PROFILE_FIELDS)


async def _load_company(db: AsyncSession, company_id: uuid.UUID) -> Company:
    company = (
        await db.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


def _to_out(company: Company) -> CompanyProfileOut:
    out = CompanyProfileOut.model_validate(company)
    out.has_logo = bool(company.logo_path)
    return out


@router.get("/profile", response_model=CompanyProfileOut)
async def get_profile(
    user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """View the company profile. Any authenticated company user."""
    company = await _load_company(db, user.company_id)
    return _to_out(company)


@router.put("/profile", response_model=CompanyProfileOut)
async def update_profile(
    body: CompanyProfileUpdate,
    user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update the company profile. Admin only. Every change is audit-logged."""
    company = await _load_company(db, user.company_id)

    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(company, field, value)

    company.profile_completed = _profile_is_complete(company)

    if changes:
        db.add(
            ActivityLog(
                company_id=company.id,
                actor_type=ActorType.company_user,
                actor_id=user.id,
                action="company.profile_updated",
                entity_type="company",
                entity_id=company.id,
                metadata_={"fields": sorted(changes.keys())},
            )
        )

    await db.commit()
    await db.refresh(company)
    return _to_out(company)


@router.post("/profile/logo", response_model=CompanyProfileOut)
async def upload_logo(
    user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Upload/replace the company logo. Admin only. PNG/JPG/SVG, <=2 MB.

    Stored encrypted-at-rest under the per-company KEK (nonce prepended to the
    ciphertext), consistent with the rest of the vault."""
    ext = LOGO_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Logo must be PNG, JPG, or SVG",
        )

    data = await file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Logo must be 2 MB or smaller",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    company = await _load_company(db, user.company_id)
    kek = await _company_kek(db, company.id)
    ciphertext, nonce = encrypt_file_data(data, kek)

    vault_dir = Path(get_settings().VAULT_STORAGE_PATH) / str(company.id)
    vault_dir.mkdir(parents=True, exist_ok=True)
    storage_path = vault_dir / f"logo_{uuid.uuid4()}.{ext}.enc"
    # Prepend the 12-byte nonce to the ciphertext.
    storage_path.write_bytes(nonce + ciphertext)

    old_path = company.logo_path
    company.logo_path = str(storage_path)
    db.add(
        ActivityLog(
            company_id=company.id,
            actor_type=ActorType.company_user,
            actor_id=user.id,
            action="company.logo_updated",
            entity_type="company",
            entity_id=company.id,
        )
    )
    await db.commit()
    await db.refresh(company)

    # Remove the previously stored logo, if any.
    if old_path and old_path != str(storage_path) and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except OSError:
            pass

    return _to_out(company)


@router.get("/profile/logo")
async def get_logo(
    user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Stream the decrypted company logo. Any authenticated company user."""
    company = await _load_company(db, user.company_id)
    if not company.logo_path or not os.path.exists(company.logo_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No logo set")

    # Derive mime from the "<uuid>.<ext>.enc" filename.
    ext = Path(company.logo_path).with_suffix("").suffix.lstrip(".")
    mime = EXT_TO_MIME.get(ext, "application/octet-stream")

    blob = Path(company.logo_path).read_bytes()
    nonce, ciphertext = blob[:12], blob[12:]
    kek = await _company_kek(db, company.id)
    data = decrypt_file_data(ciphertext, nonce, kek)

    # Neutralize any script inside an uploaded SVG (stored-XSS defense) and stop
    # content sniffing.
    headers = {
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=60",
    }
    return Response(content=data, media_type=mime, headers=headers)
