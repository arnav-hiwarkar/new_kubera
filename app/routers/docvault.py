import os
import uuid
import aiofiles
from datetime import datetime, timezone
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Response
from sqlalchemy import select, and_, or_, update, desc, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_company_user
from app.models.company import CompanyUser, CompanyKey
from app.models.docvault import Bucket, Document, DocumentVersion, DocumentStatus
from app.models.activity_log import ActivityLog, ActorType
from app.schemas.docvault import (
    BucketCreate, BucketResponse, DocumentResponse, DocumentVersionResponse, DocumentUpdate
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
    result = await db.execute(select(Bucket).where(Bucket.company_id == current_user.company_id))
    return result.scalars().all()


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
    
    # Store file locally (for V1 testing)
    # The file path format is /data/vault/{company_id}/{uuid}.enc
    vault_dir = f"/data/vault/{company_id}"
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
    query = (
        select(Document)
        .outerjoin(Bucket, Document.bucket_id == Bucket.id)
        .options(selectinload(Document.versions))
        .where(
            and_(
                Document.company_id == current_user.company_id,
                or_(
                    Document.title.ilike(search_term),
                    Document.status.cast(String).ilike(search_term),
                    func.array_to_string(Document.tags, ",").ilike(search_term),
                    Bucket.name.ilike(search_term),
                ),
            )
        )
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
        
    if updates.bucket_id:
        bucket = await db.execute(select(Bucket).where(and_(Bucket.id == updates.bucket_id, Bucket.company_id == current_user.company_id)))
        if not bucket.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid bucket")
            
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        return doc
        
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
        
    doc.status = DocumentStatus.archived
    doc.is_editable = False
    
    await log_activity(db, current_user.company_id, current_user.id, "document.archived", "document", doc.id)
    await db.commit()
    return None
