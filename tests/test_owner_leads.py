import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Lead, LeadStatus
from app.models.company import Company, CompanyUser
from tests.conftest import INTERNAL_API_KEY


@pytest.mark.asyncio
async def test_owner_leads_unauthorized(client: AsyncClient):
    resp = await client.get("/api/v1/owner/leads")
    assert resp.status_code == 422  # Missing header

    resp = await client.get(
        "/api/v1/owner/leads",
        headers={"X-Internal-Api-Key": "wrong-key"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_leads_list_and_filter(client: AsyncClient, db: AsyncSession):
    l1 = Lead(email="lead1@test.com", company_name="Co1", status=LeadStatus.new)
    l2 = Lead(email="lead2@test.com", company_name="Co2", status=LeadStatus.contacted)
    db.add_all([l1, l2])
    await db.commit()

    resp = await client.get(
        "/api/v1/owner/leads",
        headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    emails = [item["email"] for item in data]
    assert "lead1@test.com" in emails
    assert "lead2@test.com" in emails

    # Test filtering by status
    resp_filtered = await client.get(
        "/api/v1/owner/leads?status=contacted",
        headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
    )
    assert resp_filtered.status_code == 200
    filtered_data = resp_filtered.json()
    assert len(filtered_data) >= 1
    assert all(item["status"] == "contacted" for item in filtered_data)


@pytest.mark.asyncio
async def test_owner_update_lead_status(client: AsyncClient, db: AsyncSession):
    lead = Lead(email="status_test@test.com", status=LeadStatus.new)
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    resp = await client.patch(
        f"/api/v1/owner/leads/{lead.id}/status",
        json={"status": "contacted"},
        headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "contacted"


@pytest.mark.asyncio
async def test_owner_provision_company_from_lead(client: AsyncClient, db: AsyncSession):
    lead = Lead(
        email="founder_lead@innovate.com",
        company_name="Innovate Tech Private Limited",
        phone="+91 9988776655",
        status=LeadStatus.new,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    resp = await client.post(
        f"/api/v1/owner/leads/{lead.id}/provision",
        headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "Innovate Tech Private Limited"
    assert data["admin_email"] == "founder_lead@innovate.com"
    assert len(data["activation_key"]) > 10

    # Verify company and admin user created
    stmt = select(Company).where(Company.id == data["company_id"])
    res = await db.execute(stmt)
    company = res.scalar_one_or_none()
    assert company is not None
    assert company.name == "Innovate Tech Private Limited"

    stmt_user = select(CompanyUser).where(CompanyUser.email == "founder_lead@innovate.com")
    res_user = await db.execute(stmt_user)
    user = res_user.scalar_one_or_none()
    assert user is not None
    assert user.is_active is False

    # Verify lead status updated to converted
    await db.refresh(lead)
    assert lead.status == LeadStatus.converted
