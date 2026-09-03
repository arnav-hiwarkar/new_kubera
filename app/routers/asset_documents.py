"""Roled document and photograph attachment for the fixed-asset register.

Replaces the single `documents.id` FK the old asset table carried. Files still live
in DocVault — encrypted at rest with per-file DEKs — so this router reuses
`handle_file_upload` rather than inventing a second storage path.

Two consequences of that encryption worth knowing:
  * Photographs cannot be rendered with a plain <img src>. `/thumbnail` decrypts
    and streams the bytes behind normal auth.
  * Uploading needs the company KEK, so it must go through DocVault's helper.

Invoice / PO / GRN / e-way bill / approval / customs / lease attach at the
ACQUISITION level and are therefore shared by every unit exploded from it. Photos,
certificates and manuals attach per unit.
"""
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_assets_module
from app.database import get_db
from app.encryption import decrypt_dek, decrypt_file_data
from app.services.bucket_access import assert_document_attachable
from app.models.assets import (
    ACQUISITION_DOC_ROLES,
    PHOTO_DOC_ROLES,
    Asset,
    AssetAcquisition,
    AssetDocRole,
    AssetDocument,
)
from app.models.company import CompanyUser
from app.models.docvault import Bucket, Document, DocumentStatus, DocumentVersion
from app.schemas.assets import AssetDocumentAttach, AssetDocumentResponse
from app.services.activity import log_activity

router = APIRouter(prefix="/api/v1", tags=["assets"])

Reader = Annotated[CompanyUser, Depends(require_assets_module)]
Db = Annotated[AsyncSession, Depends(get_db)]

ASSET_BUCKET_NAME = "Assets"


async def _asset_bucket(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID) -> Bucket:
    """Per-company bucket that asset uploads are filed into, created on demand so
    the user never has to pick a folder from the asset form."""
    result = await db.execute(
        select(Bucket).where(Bucket.company_id == company_id, Bucket.name == ASSET_BUCKET_NAME)
    )
    bucket = result.scalar_one_or_none()
    if bucket is None:
        bucket = Bucket(company_id=company_id, name=ASSET_BUCKET_NAME, created_by=user_id)
        db.add(bucket)
        await db.flush()
    return bucket


async def _load_asset(asset_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession) -> Asset:
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.company_id == company_id)
    )
    asset = result.scalars().unique().one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


async def _load_acquisition(
    acq_id: uuid.UUID, company_id: uuid.UUID, db: AsyncSession
) -> AssetAcquisition:
    result = await db.execute(
        select(AssetAcquisition).where(
            AssetAcquisition.id == acq_id, AssetAcquisition.company_id == company_id
        )
    )
    acq = result.scalars().unique().one_or_none()
    if acq is None:
        raise HTTPException(status_code=404, detail="Acquisition not found")
    return acq


def _check_role_level(doc_role: AssetDocRole, *, on_acquisition: bool) -> None:
    """Keep shared paperwork on the acquisition and unit-specific evidence on the
    unit, so a 50-unit batch stores one invoice and fifty photographs — not fifty
    copies of the invoice."""
    if on_acquisition and doc_role not in ACQUISITION_DOC_ROLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{doc_role.value}' attaches to an individual asset, not to the acquisition"
            ),
        )
    if not on_acquisition and doc_role in ACQUISITION_DOC_ROLES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{doc_role.value}' is shared paperwork — attach it to the acquisition so every "
                "unit in the batch inherits it"
            ),
        )




async def _hydrate(db: AsyncSession, link: AssetDocument) -> AssetDocumentResponse:
    payload = AssetDocumentResponse.model_validate(link)
    row = (
        await db.execute(
            select(Document, DocumentVersion)
            .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(Document.id == link.document_id)
        )
    ).first()
    if row is not None:
        doc, version = row
        payload.title = doc.title
        if version is not None:
            payload.original_filename = version.original_filename
            payload.mime_type = version.mime_type
            payload.size_bytes = version.size_bytes
    return payload


async def _upload_and_attach(
    db: AsyncSession,
    current_user: CompanyUser,
    file: UploadFile,
    doc_role: AssetDocRole,
    title: Optional[str],
    note: Optional[str],
    asset_id: Optional[uuid.UUID],
    acquisition_id: Optional[uuid.UUID],
) -> AssetDocumentResponse:
    # Imported lazily: docvault's module-level state pulls in settings/storage that
    # we do not want at import time in tests that never upload.
    from app.routers.docvault import handle_file_upload

    bucket = await _asset_bucket(db, current_user.company_id, current_user.id)
    document = Document(
        company_id=current_user.company_id,
        bucket_id=bucket.id,
        title=(title or file.filename or doc_role.value)[:255],
        status=DocumentStatus.uploaded,
        tags=["asset", doc_role.value],
        created_by=current_user.id,
    )
    db.add(document)
    await db.flush()

    version = await handle_file_upload(
        file, document.id, current_user.company_id, current_user.id, 1, db
    )
    document.current_version_id = version.id

    link = AssetDocument(
        company_id=current_user.company_id,
        asset_id=asset_id,
        acquisition_id=acquisition_id,
        document_id=document.id,
        doc_role=doc_role,
        note=note,
        uploaded_by=current_user.id,
    )
    db.add(link)
    await log_activity(
        db,
        current_user.company_id,
        current_user.id,
        "asset_document.uploaded",
        "asset_document",
        document.id,
        {"role": doc_role.value, "asset_id": str(asset_id) if asset_id else None},
    )
    await db.commit()
    await db.refresh(link)
    return await _hydrate(db, link)


# === Asset-level ===

@router.get("/assets/{asset_id}/documents", response_model=List[AssetDocumentResponse])
async def list_asset_documents(asset_id: uuid.UUID, current_user: Reader, db: Db):
    asset = await _load_asset(asset_id, current_user.company_id, db)
    conditions = [AssetDocument.asset_id == asset.id]
    if asset.acquisition_id is not None:
        conditions.append(AssetDocument.acquisition_id == asset.acquisition_id)
    rows = await db.execute(
        select(AssetDocument).where(or_(*conditions)).order_by(AssetDocument.created_at)
    )
    return [await _hydrate(db, link) for link in rows.scalars().all()]


@router.post(
    "/assets/{asset_id}/documents",
    response_model=AssetDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_asset_document(
    asset_id: uuid.UUID, body: AssetDocumentAttach, current_user: Reader, db: Db
):
    """Link a document that is already in DocVault."""
    asset = await _load_asset(asset_id, current_user.company_id, db)
    _check_role_level(body.doc_role, on_acquisition=False)
    await assert_document_attachable(db, current_user, body.document_id)

    link = AssetDocument(
        company_id=current_user.company_id,
        asset_id=asset.id,
        document_id=body.document_id,
        doc_role=body.doc_role,
        note=body.note,
        uploaded_by=current_user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return await _hydrate(db, link)


@router.post(
    "/assets/{asset_id}/documents/upload",
    response_model=AssetDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_asset_document(
    asset_id: uuid.UUID,
    current_user: Reader,
    db: Db,
    doc_role: Annotated[AssetDocRole, Form()],
    file: Annotated[UploadFile, File()],
    title: Annotated[Optional[str], Form()] = None,
    note: Annotated[Optional[str], Form()] = None,
):
    """Upload straight from the asset page — no trip through DocVault first."""
    asset = await _load_asset(asset_id, current_user.company_id, db)
    _check_role_level(doc_role, on_acquisition=False)
    return await _upload_and_attach(
        db, current_user, file, doc_role, title, note, asset.id, None
    )


# === Acquisition-level ===

@router.post(
    "/asset-acquisitions/{acq_id}/documents",
    response_model=AssetDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_acquisition_document(
    acq_id: uuid.UUID, body: AssetDocumentAttach, current_user: Reader, db: Db
):
    acq = await _load_acquisition(acq_id, current_user.company_id, db)
    _check_role_level(body.doc_role, on_acquisition=True)
    await assert_document_attachable(db, current_user, body.document_id)

    link = AssetDocument(
        company_id=current_user.company_id,
        acquisition_id=acq.id,
        document_id=body.document_id,
        doc_role=body.doc_role,
        note=body.note,
        uploaded_by=current_user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return await _hydrate(db, link)


@router.post(
    "/asset-acquisitions/{acq_id}/documents/upload",
    response_model=AssetDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_acquisition_document(
    acq_id: uuid.UUID,
    current_user: Reader,
    db: Db,
    doc_role: Annotated[AssetDocRole, Form()],
    file: Annotated[UploadFile, File()],
    title: Annotated[Optional[str], Form()] = None,
    note: Annotated[Optional[str], Form()] = None,
):
    acq = await _load_acquisition(acq_id, current_user.company_id, db)
    _check_role_level(doc_role, on_acquisition=True)
    return await _upload_and_attach(db, current_user, file, doc_role, title, note, None, acq.id)


# === Link management + streaming ===

@router.delete("/asset-documents/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_document(link_id: uuid.UUID, current_user: Reader, db: Db):
    """Unlink from the asset. The underlying DocVault document is left alone — it
    may be referenced elsewhere, and deleting audit evidence is not this endpoint's
    job."""
    result = await db.execute(
        select(AssetDocument).where(
            AssetDocument.id == link_id, AssetDocument.company_id == current_user.company_id
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await db.delete(link)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/asset-documents/{link_id}/thumbnail")
async def stream_document(link_id: uuid.UUID, current_user: Reader, db: Db):
    """Decrypt and stream an attached file so photographs can be displayed.

    Vault files are AES-256-GCM encrypted with a per-file DEK, so there is no URL
    a browser can load directly; this is the authenticated equivalent.
    """
    import aiofiles

    from app.routers.docvault import get_company_kek

    row = (
        await db.execute(
            select(AssetDocument, DocumentVersion)
            .join(Document, Document.id == AssetDocument.document_id)
            .join(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(
                AssetDocument.id == link_id,
                AssetDocument.company_id == current_user.company_id,
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    link, version = row

    company_kek = await get_company_kek(db, current_user.company_id)
    raw_dek = decrypt_dek(version.encrypted_dek, version.dek_nonce, company_kek)
    async with aiofiles.open(version.storage_path, "rb") as f:
        blob = await f.read()
    # Layout written by handle_file_upload: 12-byte nonce, then ciphertext.
    plaintext = decrypt_file_data(blob[12:], blob[:12], raw_dek)

    disposition = "inline" if link.doc_role in PHOTO_DOC_ROLES else "attachment"
    return Response(
        content=plaintext,
        media_type=version.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{version.original_filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )
