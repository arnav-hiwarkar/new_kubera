import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStatus


@pytest.mark.asyncio
async def test_lead_model_creation_and_query(db: AsyncSession):
    lead = Lead(
        email="founder@acme.com",
        company_name="Acme Corp",
        phone="+91 9876543210",
        entities_count=3,
        notes="Interested in AuditEase and docVault for 3 entities.",
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0",
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    assert lead.id is not None
    assert lead.email == "founder@acme.com"
    assert lead.company_name == "Acme Corp"
    assert lead.status == LeadStatus.new
    assert lead.entities_count == 3
    assert lead.created_at is not None

    # Test status update
    lead.status = LeadStatus.contacted
    await db.commit()
    await db.refresh(lead)

    assert lead.status == LeadStatus.contacted

    # Query by email
    stmt = select(Lead).where(Lead.email == "founder@acme.com")
    result = await db.execute(stmt)
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.id == lead.id
