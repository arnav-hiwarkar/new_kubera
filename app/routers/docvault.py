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
from app.auth import get_current_company_user, require_admin, require_module
from app.models.company import CompanyUser, CompanyKey, UserRole
from app.models.docvault import (
    Bucket, BucketAccessGrant, BucketVisibility, Document, DocumentVersion, DocumentStatus
)
from app.models.notification import Notification, RecipientType
from app.models.activity_log import ActivityLog, ActorType
from app.schemas.docvault import (
    BucketCreate, BucketResponse, BucketUpdate, BucketAccessUpdate, DocumentResponse, DocumentVersionResponse, DocumentUpdate, DocVaultApproverResponse, DocumentReviewRequest
)
from app.encryption import (
    generate_dek, encrypt_dek, decrypt_dek, encrypt_file_data, decrypt_file_data, decrypt_company_kek
)

router = APIRouter(
    prefix="/api/v1/docvault",
    tags=["docvault"],
    dependencies=[Depends(require_module("docvault"))]
)


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


async def _attach_uploader_names(db: AsyncSession, docs: List[Document]) -> List[Document]:
    """Resolve created_by / uploaded_by / approver_id UUIDs to user names in a single query.

    The names are set as transient attributes on the ORM objects so Pydantic
    (from_attributes) picks them up. full_name is retained even for soft-deleted
    users; auditor/deleted-user uploads have a null FK and stay None.
    """
    ids = {d.created_by for d in docs if d.created_by}
    ids |= {d.approver_id for d in docs if d.approver_id}
    ids |= {v.uploaded_by for d in docs for v in d.versions if v.uploaded_by}
    names: dict[uuid.UUID, str] = {}
    if ids:
        rows = await db.execute(
            select(CompanyUser.id, CompanyUser.full_name).where(CompanyUser.id.in_(ids))
        )
        names = {row.id: row.full_name for row in rows}
    for d in docs:
        d.created_by_name = names.get(d.created_by)
        d.approver_name = names.get(d.approver_id)
        for v in d.versions:
            v.uploaded_by_name = names.get(v.uploaded_by)
    return docs


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
    current_user: Annotated[CompanyUser, Depends(require_admin)],
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


def is_company_admin(user: CompanyUser) -> bool:
    role_str = str(getattr(user.role, "value", user.role)).lower()
    return role_str == "admin" or user.role == UserRole.admin


def user_has_docvault_access(user: CompanyUser) -> bool:
    if is_company_admin(user):
        return True
    mods = user.accessible_modules or []
    if isinstance(mods, (list, tuple, set)):
        return "docvault" in mods
    if isinstance(mods, str):
        return "docvault" in mods
    return False


@router.get("/approvers", response_model=List[DocVaultApproverResponse])
async def list_docvault_approvers(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    bucket_id: Optional[uuid.UUID] = Query(None),
):
    """List eligible DocVault approvers in the company, excluding the caller.

    Open to all active company members.
    Only includes active, non-deleted users who have DocVault access (Admins or
    employees with docvault module access).
    If bucket_id is provided and the bucket is restricted, only users with access
    grants to that bucket (plus admins) are returned.
    """
    # 1. Fetch active company members excluding current user
    stmt = (
        select(CompanyUser)
        .where(
            CompanyUser.company_id == current_user.company_id,
            CompanyUser.id != current_user.id,
            CompanyUser.deleted_at.is_(None),
            CompanyUser.is_active == True,
        )
        .order_by(func.coalesce(CompanyUser.full_name, CompanyUser.email).asc())
    )
    result = await db.execute(stmt)
    all_users = result.scalars().all()

    # 2. Filter users who have docvault access
    eligible = [u for u in all_users if user_has_docvault_access(u)]

    # 3. If bucket_id is restricted, further filter to granted users + admins
    if bucket_id:
        b_res = await db.execute(
            select(Bucket).where(
                Bucket.id == bucket_id,
                Bucket.company_id == current_user.company_id,
            )
        )
        bucket = b_res.scalar_one_or_none()
        if bucket:
            vis = str(getattr(bucket.visibility, "value", bucket.visibility)).lower()
            if vis == "restricted" or bucket.visibility == BucketVisibility.restricted:
                grants_res = await db.execute(
                    select(BucketAccessGrant.company_user_id).where(
                        BucketAccessGrant.bucket_id == bucket_id
                    )
                )
                granted_ids = set(grants_res.scalars().all())
                eligible = [
                    u for u in eligible
                    if is_company_admin(u) or u.id in granted_ids
                ]

    return eligible


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
    current_user: Annotated[CompanyUser, Depends(require_admin)],
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
    is_editable: Annotated[bool, Form()] = True,
    needs_approval: Annotated[bool, Form()] = False,
    approver_id: Annotated[Optional[uuid.UUID], Form()] = None,
):
    if bucket_id:
        bucket = await db.execute(select(Bucket).where(and_(Bucket.id == bucket_id, Bucket.company_id == current_user.company_id)))
        if not bucket.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid bucket")
        if not await can_access_bucket(db, current_user, bucket_id):
            raise HTTPException(status_code=403, detail="No access to this bucket")

    initial_status = DocumentStatus.uploaded
    req_approver_id = None
    approval_req_at = None

    if needs_approval:
        if not approver_id:
            raise HTTPException(status_code=400, detail="Approver is required when requesting approval")
        approver = (await db.execute(
            select(CompanyUser).where(
                and_(
                    CompanyUser.id == approver_id,
                    CompanyUser.company_id == current_user.company_id,
                    CompanyUser.deleted_at.is_(None),
                    CompanyUser.is_active == True,
                )
            )
        )).scalar_one_or_none()
        if not approver:
            raise HTTPException(status_code=400, detail="Invalid approver selected")
        if not user_has_docvault_access(approver):
            raise HTTPException(status_code=400, detail="Selected approver does not have DocVault access")
        if bucket_id and not await can_access_bucket(db, approver, bucket_id):
            raise HTTPException(status_code=400, detail="Selected approver does not have access to this bucket")

        initial_status = DocumentStatus.pending_approval
        req_approver_id = approver_id
        approval_req_at = datetime.now(timezone.utc)

    doc = Document(
        company_id=current_user.company_id,
        bucket_id=bucket_id,
        status=initial_status,
        title=title,
        tags=[t.strip() for t in tags.split(",")] if tags else [],
        is_editable=is_editable,
        created_by=current_user.id,
        approver_id=req_approver_id,
        approval_requested_at=approval_req_at,
    )
    db.add(doc)
    await db.flush()
    
    version = await handle_file_upload(file, doc.id, current_user.company_id, current_user.id, 1, db)
    doc.current_version_id = version.id
    
    if needs_approval and req_approver_id:
        db.add(
            Notification(
                recipient_type=RecipientType.company_user,
                recipient_id=req_approver_id,
                type="docvault.approval_requested",
                payload={
                    "document_id": str(doc.id),
                    "title": doc.title,
                    "uploader_name": current_user.full_name,
                    "message": f"{current_user.full_name} requested your approval on '{doc.title}'",
                },
            )
        )

    await log_activity(db, current_user.company_id, current_user.id, "document.uploaded", "document", doc.id)
    await db.commit()
    
    # Reload with versions
    result = await db.execute(select(Document).options(selectinload(Document.versions)).where(Document.id == doc.id))
    return (await _attach_uploader_names(db, [result.scalar_one()]))[0]


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
    is_approver_or_admin = (current_user.id == doc.approver_id or is_company_admin(current_user))
    if doc.status == DocumentStatus.pending_approval and not is_approver_or_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot upload new versions while document is pending approval",
        )
        
    doc_id = doc.id
    next_version = max([v.version_number for v in doc.versions], default=0) + 1
    version = await handle_file_upload(file, doc_id, current_user.company_id, current_user.id, next_version, db)
    doc.current_version_id = version.id
    
    await log_activity(db, current_user.company_id, current_user.id, "document.version_uploaded", "document", doc_id, {"version": next_version})
    await db.commit()
    db.expire_all()

    # Reload with versions (db.refresh does not reliably reload the collection).
    result = await db.execute(
        select(Document).options(selectinload(Document.versions)).where(Document.id == doc_id)
    )
    return (await _attach_uploader_names(db, [result.scalar_one()]))[0]


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    current_user: Annotated[CompanyUser, Depends(get_current_company_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    bucket_id: Optional[uuid.UUID] = None,
    status: Optional[DocumentStatus] = None,
    tag: Optional[str] = None,
    doc_type_id: Optional[uuid.UUID] = None,
    approver_id: Optional[uuid.UUID] = None,
    pending_my_approval: Optional[bool] = None,
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
    if approver_id:
        query = query.where(Document.approver_id == approver_id)
    if pending_my_approval:
        query = query.where(and_(Document.status == DocumentStatus.pending_approval, Document.approver_id == current_user.id))
        
    query = query.order_by(desc(Document.created_at))
    result = await db.execute(query)
    return await _attach_uploader_names(db, list(result.scalars().all()))


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
    return await _attach_uploader_names(db, list(result.scalars().all()))


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
    return (await _attach_uploader_names(db, [doc]))[0]


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
        return (await _attach_uploader_names(db, [doc]))[0]

    # Approval permission guardrails: If document is pending approval, ONLY approver or admin can modify ANY property or review
    is_approver_or_admin = (current_user.id == doc.approver_id or is_company_admin(current_user))
    if doc.status == DocumentStatus.pending_approval and not is_approver_or_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned approver or an admin can modify, edit, or review this document while approval is pending",
        )

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

    if updates.approver_id:
        approver = (await db.execute(
            select(CompanyUser).where(
                and_(
                    CompanyUser.id == updates.approver_id,
                    CompanyUser.company_id == current_user.company_id,
                    CompanyUser.deleted_at.is_(None),
                    CompanyUser.is_active == True,
                )
            )
        )).scalar_one_or_none()
        if not approver:
            raise HTTPException(status_code=400, detail="Invalid approver selected")
        if not user_has_docvault_access(approver):
            raise HTTPException(status_code=400, detail="Selected approver does not have DocVault access")
        target_bucket = updates.bucket_id or doc.bucket_id
        if target_bucket and not await can_access_bucket(db, approver, target_bucket):
            raise HTTPException(status_code=400, detail="Selected approver does not have access to this bucket")

    # If transitioning away from pending_approval, record resolution timestamp and notify creator
    if doc.status == DocumentStatus.pending_approval and updates.status and updates.status != DocumentStatus.pending_approval:
        doc.approved_at = datetime.now(timezone.utc)
        if doc.created_by and doc.created_by != current_user.id:
            db.add(
                Notification(
                    recipient_type=RecipientType.company_user,
                    recipient_id=doc.created_by,
                    type="docvault.approval_resolved",
                    payload={
                        "document_id": str(doc.id),
                        "title": doc.title,
                        "status": updates.status.value,
                        "approver_name": current_user.full_name,
                        "notes": updates.approval_notes,
                        "message": f"{current_user.full_name} updated status of '{doc.title}' to {updates.status.value}",
                    },
                )
            )

    for key, value in update_data.items():
        setattr(doc, key, value)
        
    await log_activity(db, current_user.company_id, current_user.id, "document.updated", "document", doc.id, {"updated_fields": list(update_data.keys())})
    await db.commit()

    # Reload with versions (db.refresh does not reliably reload the collection).
    result = await db.execute(
        select(Document).options(selectinload(Document.versions)).where(Document.id == doc.id)
    )
    return (await _attach_uploader_names(db, [result.scalar_one()]))[0]



@router.post("/documents/{document_id}/review", response_model=DocumentResponse)
async def review_document(
    document_id: uuid.UUID,
    body: DocumentReviewRequest,
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

    if doc.status != DocumentStatus.pending_approval:
        raise HTTPException(status_code=409, detail="Document is not pending approval")

    is_admin = is_company_admin(current_user)
    if current_user.id != doc.approver_id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to review")

    if current_user.id == doc.created_by and not is_admin:
        raise HTTPException(status_code=403, detail="Uploader cannot review their own document")

    old_status = doc.status.value if doc.status else None
    
    doc.status = DocumentStatus(body.decision)
    doc.approval_notes = body.approval_notes
    doc.approved_by = current_user.id
    doc.approved_at = datetime.now(timezone.utc)

    if doc.created_by and doc.created_by != current_user.id:
        db.add(
            Notification(
                recipient_type=RecipientType.company_user,
                recipient_id=doc.created_by,
                type="docvault.approval_resolved",
                payload={
                    "document_id": str(doc.id),
                    "title": doc.title,
                    "status": doc.status.value,
                    "approver_name": current_user.full_name,
                    "notes": doc.approval_notes,
                    "message": f"{current_user.full_name} updated status of '{doc.title}' to {doc.status.value}",
                },
            )
        )

    await log_activity(
        db, current_user.company_id, current_user.id, "document.reviewed", "document", doc.id,
        {"from": old_status, "to": doc.status.value, "notes": doc.approval_notes}
    )
    
    await db.commit()

    result = await db.execute(
        select(Document).options(selectinload(Document.versions)).where(Document.id == doc.id)
    )
    return (await _attach_uploader_names(db, [result.scalar_one()]))[0]


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

    is_approver_or_admin = (current_user.id == doc.approver_id or is_company_admin(current_user))
    if doc.status == DocumentStatus.pending_approval and not is_approver_or_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot archive or delete a document while approval is pending",
        )

    doc.status = DocumentStatus.archived
    doc.is_editable = False
    
    await log_activity(db, current_user.company_id, current_user.id, "document.archived", "document", doc.id)
    await db.commit()
    return None
