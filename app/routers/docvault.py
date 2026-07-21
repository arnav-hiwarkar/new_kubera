import os
import uuid
import aiofiles
from datetime import datetime, timezone
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Response
from sqlalchemy import select, and_, or_, update, delete, desc, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.auth import get_current_company_user, require_admin
from app.models.company import CompanyUser, CompanyKey, UserRole
from app.models.docvault import (
    Bucket, BucketAccessGrant, BucketVisibility, Document, DocumentVersion, DocumentStatus
)
from app.models.activity_log import ActivityLog, ActorType
from app.schemas.docvault import (
    BucketCreate, BucketResponse, BucketUpdate, BucketAccessUpdate, DocumentResponse, DocumentVersionResponse, DocumentUpdate
)
from app.encryption import (
    generate_dek, encrypt_dek, decrypt_dek, encrypt_file_data, decrypt_file_data, decrypt_company_kek
)

router = APIRouter(prefix="/api/v1/docvault", tags=["docvault"])


async def log_activity(db: AsyncSession, company_id: uuid.UUID, actor_id: uuid.UUID, action: str, entity_type: str, entity_id: uuid.UUID, metadata_: dict = None):
    log = ActivityLog(
        company_id=company_id,
        actor_type=ActorType.company_user,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=metadata_
    )
    db.add(log)


async def get_company_kek(db: AsyncSession, company_id: uuid.UUID) -> bytes:
    result = await db.execute(select(CompanyKey).where(CompanyKey.company_id == company_id))
    key_record = result.scalar_one_or_none()
    if not key_record:
        raise HTTPException(status_code=500, detail="Company encryption key not found")
    return decrypt_company_kek(key_record.encrypted_kek, key_record.kek_nonce)


async def accessible_bucket_ids(db: AsyncSession, user: CompanyUser) -> Optional[set[uuid.UUID]]:
    """Bucket ids the user may see within their company.

    Returns None for admins (unrestricted — no filtering should be applied).
    For non-admins, returns the set of bucket ids that are either visible to
    everyone or explicitly granted to the user. A restricted bucket is visible
    strictly to admins + the users on its access list — creating a bucket does
    not, on its own, grant continued access once it is restricted.
    """
    if user.role == UserRole.admin:
        return None
    result = await db.execute(
        select(Bucket.id)
        .outerjoin(
            BucketAccessGrant,
            and_(
                BucketAccessGrant.bucket_id == Bucket.id,
                BucketAccessGrant.company_user_id == user.id,
            ),
        )
        .where(
            and_(
                Bucket.company_id == user.company_id,
                or_(
                    Bucket.visibility == BucketVisibility.everyone,
                    BucketAccessGrant.id.isnot(None),
                ),
            )
        )
    )
    return set(result.scalars().all())


def _document_bucket_filter(accessible: Optional[set[uuid.UUID]]):
    """SQL predicate limiting documents to accessible buckets. Uncategorized
    documents (no bucket) are visible to everyone. None => no restriction."""
    if accessible is None:
        return None
    return or_(Document.bucket_id.is_(None), Document.bucket_id.in_(accessible))


async def can_access_bucket(db: AsyncSession, user: CompanyUser, bucket_id: Optional[uuid.UUID]) -> bool:
    """Whether the user may use `bucket_id` (None = uncategorized, always allowed)."""
    if bucket_id is None:
        return True
    accessible = await accessible_bucket_ids(db, user)
    if accessible is None:
        return True
    return bucket_id in accessible


# --- Buckets ---

@router.post("/buckets", response_model=BucketResponse, status_code=status.HTTP_201_CREATED)
async def create_bucket(
    bucket: BucketCreate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    new_bucket = Bucket(
        name=bucket.name,
        company_id=current_user.company_id,
        created_by=current_user.id
    )
    db.add(new_bucket)
    await db.flush()
    await log_activity(db, current_user.company_id, current_user.id, "bucket.created", "bucket", new_bucket.id, {"name": bucket.name})
    await db.commit()
    await db.refresh(new_bucket)
    return new_bucket


@router.get("/buckets", response_model=List[BucketResponse])
async def list_buckets(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    query = select(Bucket).where(Bucket.company_id == current_user.company_id)
    accessible = await accessible_bucket_ids(db, current_user)
    if accessible is not None:
        query = query.where(Bucket.id.in_(accessible))
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/buckets/{bucket_id}", response_model=BucketResponse)
async def rename_bucket(
    bucket_id: uuid.UUID,
    body: BucketUpdate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Rename a bucket. Admin only. Documents need no change — they resolve the
    bucket name via `bucket_id`, so the rename is reflected everywhere at once."""
    result = await db.execute(
        select(Bucket).where(and_(Bucket.id == bucket_id, Bucket.company_id == current_user.company_id))
    )
    bucket = result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket not found")

    old_name = bucket.name
    bucket.name = body.name
    await log_activity(
        db, current_user.company_id, current_user.id, "bucket.renamed", "bucket", bucket_id,
        {"from": old_name, "to": body.name},
    )
    await db.commit()
    await db.refresh(bucket)
    return bucket


@router.patch("/buckets/{bucket_id}/access", response_model=BucketResponse)
async def update_bucket_access(
    bucket_id: uuid.UUID,
    body: BucketAccessUpdate,
    current_user: Annotated[CompanyUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Set a bucket's visibility and, for `restricted`, the exact list of users
    granted access. Admin only. Replaces any existing grants."""
    result = await db.execute(
        select(Bucket).where(and_(Bucket.id == bucket_id, Bucket.company_id == current_user.company_id))
    )
    bucket = result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket not found")

    bucket.visibility = body.visibility

    # Rebuild the grant set from scratch. Grants only matter for `restricted`;
    # for `everyone` we clear them so the bucket is open to all.
    await db.execute(delete(BucketAccessGrant).where(BucketAccessGrant.bucket_id == bucket_id))

    granted_ids: List[uuid.UUID] = []
    if body.visibility == BucketVisibility.restricted and body.user_ids:
        # Only keep ids that are real, live users of this company.
        valid = await db.execute(
            select(CompanyUser.id).where(
                and_(
                    CompanyUser.id.in_(body.user_ids),
                    CompanyUser.company_id == current_user.company_id,
                    CompanyUser.deleted_at.is_(None),
                )
            )
        )
        granted_ids = list(valid.scalars().all())
        for uid in granted_ids:
            db.add(BucketAccessGrant(bucket_id=bucket_id, company_user_id=uid))

    await log_activity(
        db, current_user.company_id, current_user.id, "bucket.access_updated", "bucket", bucket_id,
        {"visibility": body.visibility.value, "user_ids": [str(u) for u in granted_ids]},
    )
    await db.commit()
    await db.refresh(bucket)
    return bucket


@router.delete("/buckets/{bucket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bucket(
    bucket_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(Bucket).where(and_(Bucket.id == bucket_id, Bucket.company_id == current_user.company_id)))
    bucket = result.scalar_one_or_none()
    if not bucket:
        raise HTTPException(status_code=404, detail="Bucket not found")
    if not await can_access_bucket(db, current_user, bucket_id):
        raise HTTPException(status_code=404, detail="Bucket not found")

    # Check if bucket has documents
    docs = await db.execute(select(Document.id).where(Document.bucket_id == bucket_id).limit(1))
    if docs.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Bucket is not empty")
        
    await db.delete(bucket)
    await log_activity(db, current_user.company_id, current_user.id, "bucket.deleted", "bucket", bucket.id)
    await db.commit()
    return None


# --- Documents ---

async def handle_file_upload(
    file: UploadFile,
    document_id: uuid.UUID,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    version_number: int,
    db: AsyncSession
) -> DocumentVersion:
    # Read file data
    file_data = await file.read()
    
    # Generate DEK and encrypt data
    raw_dek, dek_nonce_for_encryption = generate_dek()
    ciphertext, file_nonce = encrypt_file_data(file_data, raw_dek)
    
    # Encrypt DEK under KEK
    company_kek = await get_company_kek(db, company_id)
    encrypted_dek, dek_nonce_for_kek = encrypt_dek(raw_dek, company_kek)
    
    # Store file locally (for V1 testing).
    # Path format is {VAULT_STORAGE_PATH}/{company_id}/{uuid}.enc (default /data/vault).
    vault_dir = f"{get_settings().VAULT_STORAGE_PATH}/{company_id}"
    os.makedirs(vault_dir, exist_ok=True)
    
    file_uuid = str(uuid.uuid4())
    storage_path = f"{vault_dir}/{file_uuid}.enc"
    
    # Write ciphertext and the file nonce to disk. Actually, since file_nonce is needed, we should save it.
    # Wait, the encrypt_file_data returns (ciphertext, nonce). The nonce is 12 bytes. 
    # Let's just prepend the 12-byte nonce to the ciphertext in the file.
    async with aiofiles.open(storage_path, "wb") as f:
        await f.write(file_nonce + ciphertext)
        
    import hashlib
    checksum = hashlib.sha256(file_data).hexdigest()

    version = DocumentVersion(
        document_id=document_id,
        storage_path=storage_path,
        original_filename=file.filename or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(file_data),
        checksum=checksum,
        encrypted_dek=encrypted_dek,
        dek_nonce=dek_nonce_for_kek,
        uploaded_by=user_id,
        version_number=version_number
    )
    db.add(version)
    await db.flush()
    return version


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    bucket_id: Annotated[Optional[uuid.UUID], Form()] = None,
    tags: Annotated[Optional[str], Form()] = None, # comma-separated
    is_editable: Annotated[bool, Form()] = True
):
    if bucket_id:
        bucket = await db.execute(select(Bucket).where(and_(Bucket.id == bucket_id, Bucket.company_id == current_user.company_id)))
        if not bucket.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid bucket")
        if not await can_access_bucket(db, current_user, bucket_id):
            raise HTTPException(status_code=403, detail="No access to this bucket")

    doc = Document(
        company_id=current_user.company_id,
        bucket_id=bucket_id,
        title=title,
        tags=[t.strip() for t in tags.split(",")] if tags else [],
        is_editable=is_editable,
        created_by=current_user.id
    )
    db.add(doc)
    await db.flush()
    
    version = await handle_file_upload(file, doc.id, current_user.company_id, current_user.id, 1, db)
    doc.current_version_id = version.id
    
    await log_activity(db, current_user.company_id, current_user.id, "document.uploaded", "document", doc.id)
    await db.commit()
    
    # Reload with versions
    result = await db.execute(select(Document).options(selectinload(Document.versions)).where(Document.id == doc.id))
    return result.scalar_one()


@router.post("/documents/{document_id}/versions", response_model=DocumentResponse)
async def upload_document_version(
    document_id: uuid.UUID,
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(and_(Document.id == document_id, Document.company_id == current_user.company_id))
    )
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, current_user, doc.bucket_id):
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.is_editable:
        raise HTTPException(status_code=409, detail="Document is not editable")
        
    next_version = max([v.version_number for v in doc.versions], default=0) + 1
    version = await handle_file_upload(file, doc.id, current_user.company_id, current_user.id, next_version, db)
    doc.current_version_id = version.id
    
    await log_activity(db, current_user.company_id, current_user.id, "document.version_uploaded", "document", doc.id, {"version": next_version})
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    bucket_id: Optional[uuid.UUID] = None,
    status: Optional[DocumentStatus] = None,
    tag: Optional[str] = None,
    doc_type_id: Optional[uuid.UUID] = None
):
    query = select(Document).options(selectinload(Document.versions)).where(Document.company_id == current_user.company_id)
    accessible = await accessible_bucket_ids(db, current_user)
    bucket_filter = _document_bucket_filter(accessible)
    if bucket_filter is not None:
        query = query.where(bucket_filter)
    if bucket_id:
        query = query.where(Document.bucket_id == bucket_id)
    if status:
        query = query.where(Document.status == status)
    if tag:
        query = query.where(Document.tags.any(tag))
    if doc_type_id:
        query = query.where(Document.doc_type_id == doc_type_id)
        
    query = query.order_by(desc(Document.created_at))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/documents/search", response_model=List[DocumentResponse])
async def search_documents(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(..., min_length=2)
):
    # Basic ILIKE search on title, tags, status, and bucket name
    search_term = f"%{q}%"
    conditions = [
        Document.company_id == current_user.company_id,
        or_(
            Document.title.ilike(search_term),
            Document.status.cast(String).ilike(search_term),
            func.array_to_string(Document.tags, ",").ilike(search_term),
            Bucket.name.ilike(search_term),
        ),
    ]
    accessible = await accessible_bucket_ids(db, current_user)
    bucket_filter = _document_bucket_filter(accessible)
    if bucket_filter is not None:
        conditions.append(bucket_filter)
    query = (
        select(Document)
        .outerjoin(Bucket, Document.bucket_id == Bucket.id)
        .options(selectinload(Document.versions))
        .where(and_(*conditions))
        .order_by(desc(Document.created_at))
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(and_(Document.id == document_id, Document.company_id == current_user.company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, current_user, doc.bucket_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    version_id: Optional[uuid.UUID] = None
):
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(and_(Document.id == document_id, Document.company_id == current_user.company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, current_user, doc.bucket_id):
        raise HTTPException(status_code=404, detail="Document not found")

    if version_id:
        version = next((v for v in doc.versions if v.id == version_id), None)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")
    else:
        if not doc.current_version_id:
            raise HTTPException(status_code=404, detail="No versions available")
        version = next((v for v in doc.versions if v.id == doc.current_version_id), None)
        
    company_kek = await get_company_kek(db, current_user.company_id)
    raw_dek = decrypt_dek(version.encrypted_dek, version.dek_nonce, company_kek)
    
    async with aiofiles.open(version.storage_path, "rb") as f:
        file_content = await f.read()
        
    nonce = file_content[:12]
    ciphertext = file_content[12:]
    
    plaintext = decrypt_file_data(ciphertext, nonce, raw_dek)
    
    await log_activity(db, current_user.company_id, current_user.id, "document.downloaded", "document", doc.id, {"version_id": str(version.id)})
    
    return Response(
        content=plaintext, 
        media_type=version.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{version.original_filename}"'}
    )


@router.patch("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    updates: DocumentUpdate,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.versions))
        .where(and_(Document.id == document_id, Document.company_id == current_user.company_id))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, current_user, doc.bucket_id):
        raise HTTPException(status_code=404, detail="Document not found")

    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        return doc

    # A locked (non-editable) document freezes its content/metadata — title, tags
    # and bucket. Status changes (incl. archive) and toggling is_editable back on
    # are always allowed. A request that re-enables editing in the same call may
    # also change the gated fields.
    GATED = {"title", "tags", "bucket_id"}
    effective_editable = update_data.get("is_editable", doc.is_editable)
    if not effective_editable and GATED & update_data.keys():
        raise HTTPException(status_code=409, detail="Document is not editable")

    if updates.bucket_id:
        bucket = await db.execute(select(Bucket).where(and_(Bucket.id == updates.bucket_id, Bucket.company_id == current_user.company_id)))
        if not bucket.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid bucket")
        if not await can_access_bucket(db, current_user, updates.bucket_id):
            raise HTTPException(status_code=403, detail="No access to this bucket")

    for key, value in update_data.items():
        setattr(doc, key, value)
        
    await log_activity(db, current_user.company_id, current_user.id, "document.updated", "document", doc.id, {"updated_fields": list(update_data.keys())})
    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    result = await db.execute(select(Document).where(and_(Document.id == document_id, Document.company_id == current_user.company_id)))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, current_user, doc.bucket_id):
        raise HTTPException(status_code=404, detail="Document not found")

    doc.status = DocumentStatus.archived
    doc.is_editable = False
    
    await log_activity(db, current_user.company_id, current_user.id, "document.archived", "document", doc.id)
    await db.commit()
    return None
