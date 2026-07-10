import pytest
from tests.conftest import create_test_company, get_company_token, create_test_auditor, get_auditor_token

@pytest.mark.asyncio
async def test_duplicate_invite_rejected(client, clean_tables):
    # 1. Create company and get token
    await create_test_company(client, email="admin@dup.com", password="testpass123")
    company_token = await get_company_token(client, email="admin@dup.com", password="testpass123")
    company_headers = {"Authorization": f"Bearer {company_token}"}

    # 2. Create an engagement
    r = await client.post("/api/v1/auditease/engagements", json={"period_label": "Test Period 2026"}, headers=company_headers)
    assert r.status_code == 201
    eng_id = r.json()["id"]

    # 3. Register a NEW auditor
    await create_test_auditor(client, email="auditor@dup.com", password="testpass123", name="Test Auditor")

    # 4. Invite the existing auditor
    r = await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "auditor@dup.com"}, headers=company_headers)
    assert r.status_code == 200

    # 5. Try to invite the same auditor again
    r = await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "auditor@dup.com"}, headers=company_headers)
    assert r.status_code == 400
    assert "already invited" in r.json()["detail"]
