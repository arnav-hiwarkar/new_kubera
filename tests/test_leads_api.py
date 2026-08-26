import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStatus


@pytest.mark.asyncio
async def test_submit_lead_success(client: AsyncClient, db: AsyncSession):
    resp = await client.post(
        "/api/v1/leads/interest",
        json={
            "email": "CFO@AcmeCorp.com ",
            "company_name": "Acme Corp Ltd",
            "phone": "+91 9876543210",
            "entities_count": 4,
            "notes": "Looking for compliance automation for 4 entities.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "received"
    assert "Thank you" in data["message"]

    # Verify database insertion with normalized email
    stmt = select(Lead).where(Lead.email == "cfo@acmecorp.com")
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    assert lead is not None
    assert lead.company_name == "Acme Corp Ltd"
    assert lead.status == LeadStatus.new
    assert lead.entities_count == 4


@pytest.mark.asyncio
async def test_submit_lead_honeypot_silently_drops(client: AsyncClient, db: AsyncSession):
    resp = await client.post(
        "/api/v1/leads/interest",
        json={
            "email": "spambot@malicious.com",
            "website_url_hp": "http://spam-link.ru",  # Honeypot filled by bot
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"

    # Verify NOTHING was inserted into DB
    stmt = select(Lead).where(Lead.email == "spambot@malicious.com")
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    assert lead is None


@pytest.mark.asyncio
async def test_submit_lead_invalid_email(client: AsyncClient):
    resp = await client.post(
        "/api/v1/leads/interest",
        json={"email": "not-an-email"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_lead_anti_enumeration(client: AsyncClient, db: AsyncSession):
    # Submit once
    r1 = await client.post(
        "/api/v1/leads/interest",
        json={"email": "repeat@example.com"},
    )
    # Submit second time
    r2 = await client.post(
        "/api/v1/leads/interest",
        json={"email": "repeat@example.com"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
