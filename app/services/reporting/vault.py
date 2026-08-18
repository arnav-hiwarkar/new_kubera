"""docVault archival integration for generated reports."""
from __future__ import annotations

import io
import uuid
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile

from app.models.docvault import Bucket, Document, DocumentStatus
from app.routers.docvault import handle_file_upload


class _BytesUploadAdapter:
    """Lightweight adapter exposing async read(), filename, and content_type for handle_file_upload."""
    def __init__(self, content: bytes, filename: str, mime_type: str):
        self._content = content
        self.filename = filename
        self.content_type = mime_type

    async def read(self) -> bytes:
        return self._content


async def archive_report(
    db: AsyncSession,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    bucket_name: str,
    filename: str,
    content: bytes,
    mime_type: str,
) -> Document:
    """Archive a rendered report directly into a docVault bucket using standard encryption.
    
    Reuses handle_file_upload to avoid duplicating DEK/KEK encryption logic and path generation.
    """
    # 1. Find or create the target bucket
    bucket_res = await db.execute(
        select(Bucket).where(
            and_(Bucket.company_id == company_id, Bucket.name == bucket_name)
        )
    )
    bucket = bucket_res.scalar_one_or_none()
    if not bucket:
        bucket = Bucket(company_id=company_id, name=bucket_name, created_by=user_id)
        db.add(bucket)
        await db.flush()

    # 2. Create the Document entity (locked against inline editing)
    doc = Document(
        company_id=company_id,
        bucket_id=bucket.id,
        title=filename,
        status=DocumentStatus.uploaded,
        created_by=user_id,
        is_editable=False,
    )
    db.add(doc)
    await db.flush()

    # 3. Encrypt and persist file data via docVault's handle_file_upload
    file_adapter = _BytesUploadAdapter(content, filename, mime_type)
    version = await handle_file_upload(
        file=file_adapter,  # type: ignore[arg-type]
        document_id=doc.id,
        company_id=company_id,
        user_id=user_id,
        version_number=1,
        db=db,
    )

    doc.current_version_id = version.id
    await db.commit()
    return doc
