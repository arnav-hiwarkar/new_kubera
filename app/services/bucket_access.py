"""Bucket-level access checks shared across DocVault and every other router that
attaches an existing DocVault document (Assets, AuditEase). See
docs/superpowers/specs/2026-09-03-docvault-attach-gating-design.md."""
import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import user_has_module
from app.models.company import CompanyUser, UserRole
from app.models.docvault import Bucket, BucketAccessGrant, BucketVisibility, Document


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


async def assert_document_attachable(
    db: AsyncSession, user: CompanyUser, document_id: uuid.UUID
) -> Document:
    """Raise 403/404 unless `user` may attach `document_id` to something outside
    DocVault (an asset, an AuditEase query, a requirement response). Admins
    bypass both the module and bucket checks."""
    if not user_has_module(user, "docvault"):
        raise HTTPException(status_code=403, detail="No access to the docvault module")
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.company_id == user.company_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not await can_access_bucket(db, user, doc.bucket_id):
        raise HTTPException(status_code=403, detail="You don't have access to this document")
    return doc
