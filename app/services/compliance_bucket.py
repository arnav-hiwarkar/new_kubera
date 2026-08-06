"""The docVault bucket each compliance domain files its documents into.

Bucket resolution used to live in the browser, matching on the literal bucket
name. Sync detection needs a link the backend owns, so the canonical names live
here and both the compliance router and the record upload flow go through this.
"""
import uuid
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance import ComplianceDomain
from app.models.docvault import Bucket

# These match the names the frontend has been creating, so existing buckets are
# adopted rather than duplicated.
COMPLIANCE_BUCKET_NAMES: dict[ComplianceDomain, str] = {
    ComplianceDomain.secretarial: "SecretarialEase",
    ComplianceDomain.roc: "ROC Compliance",
}


async def ensure_compliance_bucket(
    db: AsyncSession,
    company_id: uuid.UUID,
    domain: ComplianceDomain,
    created_by: Optional[uuid.UUID] = None,
) -> Bucket:
    """Find the domain's bucket for this company, creating it if absent."""
    name = COMPLIANCE_BUCKET_NAMES[domain]
    res = await db.execute(
        select(Bucket).where(and_(Bucket.company_id == company_id, Bucket.name == name))
    )
    bucket = res.scalar_one_or_none()
    if bucket:
        return bucket
    bucket = Bucket(company_id=company_id, name=name, created_by=created_by)
    db.add(bucket)
    await db.flush()
    return bucket


async def find_compliance_bucket(
    db: AsyncSession, company_id: uuid.UUID, domain: ComplianceDomain
) -> Optional[Bucket]:
    """Look up the bucket without creating it — for read-only paths."""
    res = await db.execute(
        select(Bucket).where(
            and_(Bucket.company_id == company_id, Bucket.name == COMPLIANCE_BUCKET_NAMES[domain])
        )
    )
    return res.scalar_one_or_none()
