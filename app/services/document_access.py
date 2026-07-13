"""Auditor document access + query/requirement attachment routing.

All attachments (requirement fulfilments and query files) are docVault `documents`.
Files uploaded from a filesystem — by either party — become company-owned encrypted
documents in a system "Audit Attachments" bucket, then the auditor is granted read.
"""
import uuid
from typing import Optional

from fastapi import UploadFile
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.docvault import Bucket, Document, DocumentAccessOverride, PrincipalType
from app.models.auditease import AuditEngagement, AuditorEngagementGrant, GrantStatus

AUDIT_BUCKET_NAME = "Audit Attachments"


async def ensure_audit_bucket(db: AsyncSession, company_id: uuid.UUID, created_by: Optional[uuid.UUID] = None) -> Bucket:
    res = await db.execute(
        select(Bucket).where(and_(Bucket.company_id == company_id, Bucket.name == AUDIT_BUCKET_NAME))
    )
    bucket = res.scalar_one_or_none()
    if bucket:
        return bucket
    bucket = Bucket(company_id=company_id, name=AUDIT_BUCKET_NAME, created_by=created_by)
    db.add(bucket)
    await db.flush()
    return bucket


async def grant_auditor_read(db: AsyncSession, document_id: uuid.UUID, auditor_id: uuid.UUID) -> None:
    """Idempotently grant an auditor read access to a document."""
    res = await db.execute(
        select(DocumentAccessOverride.id).where(
            and_(
                DocumentAccessOverride.document_id == document_id,
                DocumentAccessOverride.principal_type == PrincipalType.auditor,
                DocumentAccessOverride.principal_id == auditor_id,
            )
        ).limit(1)
    )
    if res.first():
        return
    db.add(DocumentAccessOverride(
        document_id=document_id,
        principal_type=PrincipalType.auditor,
        principal_id=auditor_id,
        permission_level="read",
    ))


async def create_attachment_document(
    db: AsyncSession,
    company_id: uuid.UUID,
    file: UploadFile,
    created_by: Optional[uuid.UUID],
    grant_auditor_id: Optional[uuid.UUID],
) -> Document:
    """Upload a filesystem file into the company's Audit Attachments bucket and,
    if given, grant the auditor read. Returns the created Document."""
    from app.routers.docvault import handle_file_upload  # lazy import to avoid cycle

    bucket = await ensure_audit_bucket(db, company_id, created_by)
    doc = Document(
        company_id=company_id,
        bucket_id=bucket.id,
        title=file.filename or "attachment",
        tags=["audit-attachment"],
        is_editable=False,
        created_by=created_by,
    )
    db.add(doc)
    await db.flush()
    version = await handle_file_upload(file, doc.id, company_id, created_by, 1, db)
    doc.current_version_id = version.id
    if grant_auditor_id:
        await grant_auditor_read(db, doc.id, grant_auditor_id)
    return doc


async def auditor_can_access_document(
    db: AsyncSession, auditor_id: uuid.UUID, document_id: uuid.UUID
) -> Optional[Document]:
    """A document the auditor may read: it has an auditor override AND the auditor
    still holds a non-revoked grant to an engagement of that document's company
    (so access ends when the engagement closes)."""
    res = await db.execute(select(Document).where(Document.id == document_id))
    doc = res.scalar_one_or_none()
    if not doc:
        return None

    ov = await db.execute(
        select(DocumentAccessOverride.id).where(
            and_(
                DocumentAccessOverride.document_id == document_id,
                DocumentAccessOverride.principal_type == PrincipalType.auditor,
                DocumentAccessOverride.principal_id == auditor_id,
            )
        ).limit(1)
    )
    if not ov.first():
        return None

    grant = await db.execute(
        select(AuditorEngagementGrant.id)
        .join(AuditEngagement, AuditEngagement.id == AuditorEngagementGrant.engagement_id)
        .where(
            and_(
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
                AuditEngagement.company_id == doc.company_id,
            )
        )
        .limit(1)
    )
    if not grant.first():
        return None
    return doc
