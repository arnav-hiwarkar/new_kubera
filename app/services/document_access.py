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

from app.models.docvault import Bucket, BucketAccessGrant, BucketVisibility, Document, DocumentAccessOverride, PrincipalType
from app.models.auditease import (
    AuditEngagement,
    AuditorEngagementGrant,
    GrantStatus,
    EngagementStatus,
    RequirementRequest,
    RequirementResponse,
    RequirementResponseDocument,
    Query,
    QueryMessage,
)
from app.services.auditor_access import area_enabled

AUDIT_BUCKET_NAME = "Audit Attachments"


async def ensure_audit_bucket(
    db: AsyncSession,
    company_id: uuid.UUID,
    created_by: Optional[uuid.UUID] = None,
    engagement_id: Optional[uuid.UUID] = None,
) -> Bucket:
    bucket_name = AUDIT_BUCKET_NAME
    if engagement_id:
        res_eng = await db.execute(
            select(AuditEngagement.period_label).where(
                and_(
                    AuditEngagement.id == engagement_id,
                    AuditEngagement.company_id == company_id,
                )
            )
        )
        label = res_eng.scalar_one_or_none()
        if label:
            bucket_name = f"Audit - {label}"

    res = await db.execute(
        select(Bucket).where(and_(Bucket.company_id == company_id, Bucket.name == bucket_name))
    )
    bucket = res.scalar_one_or_none()
    if bucket:
        if bucket.visibility != BucketVisibility.everyone:
            bucket.visibility = BucketVisibility.everyone
            await db.flush()
        return bucket
    bucket = Bucket(
        company_id=company_id,
        name=bucket_name,
        created_by=created_by,
        visibility=BucketVisibility.everyone,
    )
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
    engagement_id: Optional[uuid.UUID] = None,
) -> Document:
    """Upload a filesystem file into the company's dedicated Audit bucket and,
    if given, grant the auditor read. Returns the created Document."""
    from app.routers.docvault import handle_file_upload  # lazy import to avoid cycle

    bucket = await ensure_audit_bucket(db, company_id, created_by, engagement_id=engagement_id)
    doc = Document(
        company_id=company_id,
        bucket_id=bucket.id,
        title=file.filename or "attachment",
        tags=["audit-attachment"] + ([f"engagement:{engagement_id}"] if engagement_id else []),
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
    """A document the auditor may read: it is attached to a requirement response or query
    in an active engagement the auditor holds a grant to, or has an explicit DocumentAccessOverride."""
    res = await db.execute(select(Document).where(Document.id == document_id))
    doc = res.scalar_one_or_none()
    if not doc:
        return None

    # Check 1: Document attached to a requirement response in an active engagement for this auditor
    res_req = await db.execute(
        select(AuditEngagement.id, AuditorEngagementGrant.area_permissions)
        .join(AuditorEngagementGrant, AuditorEngagementGrant.engagement_id == AuditEngagement.id)
        .join(RequirementRequest, RequirementRequest.engagement_id == AuditEngagement.id)
        .join(RequirementResponse, RequirementResponse.requirement_id == RequirementRequest.id)
        .join(RequirementResponseDocument, RequirementResponseDocument.response_id == RequirementResponse.id)
        .where(
            and_(
                RequirementResponseDocument.document_id == document_id,
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
                AuditEngagement.status != EngagementStatus.closed,
            )
        )
    )
    req_grants = res_req.all()
    if any(area_enabled(perms, "requirements") or area_enabled(perms, "documents") for _, perms in req_grants):
        return doc

    # Check 2: Document attached to a query message in an active engagement for this auditor
    res_query = await db.execute(
        select(AuditEngagement.id, AuditorEngagementGrant.area_permissions)
        .join(AuditorEngagementGrant, AuditorEngagementGrant.engagement_id == AuditEngagement.id)
        .join(Query, Query.engagement_id == AuditEngagement.id)
        .join(QueryMessage, QueryMessage.query_id == Query.id)
        .where(
            and_(
                QueryMessage.attached_document_id == document_id,
                AuditorEngagementGrant.auditor_id == auditor_id,
                AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
                AuditEngagement.status != EngagementStatus.closed,
            )
        )
    )
    query_grants = res_query.all()
    if any(area_enabled(perms, "queries") or area_enabled(perms, "documents") for _, perms in query_grants):
        return doc

    # Check 3: Explicit DocumentAccessOverride with active engagement
    ov = await db.execute(
        select(DocumentAccessOverride.id).where(
            and_(
                DocumentAccessOverride.document_id == document_id,
                DocumentAccessOverride.principal_type == PrincipalType.auditor,
                DocumentAccessOverride.principal_id == auditor_id,
            )
        ).limit(1)
    )
    if ov.first():
        grant = await db.execute(
            select(AuditorEngagementGrant.area_permissions)
            .join(AuditEngagement, AuditEngagement.id == AuditorEngagementGrant.engagement_id)
            .where(
                and_(
                    AuditorEngagementGrant.auditor_id == auditor_id,
                    AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
                    AuditEngagement.company_id == doc.company_id,
                    AuditEngagement.status != EngagementStatus.closed,
                )
            )
        )
        all_perms = grant.scalars().all()
        if any(area_enabled(p, "documents") or area_enabled(p, "requirements") or area_enabled(p, "queries") for p in all_perms):
            return doc

    return None


async def grant_document_access_to_auditors(
    db: AsyncSession, engagement_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Give every accepted or invited auditor with the requirements area read access to a
    submitted document (shared-workspace rule)."""
    rows = (await db.execute(
        select(AuditorEngagementGrant.auditor_id, AuditorEngagementGrant.area_permissions)
        .where(and_(
            AuditorEngagementGrant.engagement_id == engagement_id,
            AuditorEngagementGrant.status.in_([GrantStatus.invited, GrantStatus.accepted]),
        )))).all()
    existing = set((await db.execute(
        select(DocumentAccessOverride.principal_id).where(
            DocumentAccessOverride.document_id == document_id,
            DocumentAccessOverride.principal_type == PrincipalType.auditor,
        ))).scalars().all())
    for auditor_id, perms in rows:
        if not (area_enabled(perms, "requirements") or area_enabled(perms, "documents")) or auditor_id in existing:
            continue
        db.add(DocumentAccessOverride(
            document_id=document_id,
            principal_type=PrincipalType.auditor,
            principal_id=auditor_id,
            permission_level="read",
        ))

