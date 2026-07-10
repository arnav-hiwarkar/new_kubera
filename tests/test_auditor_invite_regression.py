import pytest
from tests.conftest import create_test_company, get_company_token, create_test_auditor, get_auditor_token

@pytest.mark.asyncio
async def test_invite_existing_auditor(client, clean_tables):
    # 1. Create company and get token
    await create_test_company(client, email="admin@testco.com", password="testpass123")
    company_token = await get_company_token(client, email="admin@testco.com", password="testpass123")
    company_headers = {"Authorization": f"Bearer {company_token}"}

    # 2. Create an engagement
    r = await client.post("/api/v1/auditease/engagements", json={"period_label": "Test Period 2026"}, headers=company_headers)
    assert r.status_code == 201
    eng_id = r.json()["id"]

    # 3. Register a NEW auditor
    await create_test_auditor(client, email="new.test.auditor@auditor.com", password="testpass123", name="Test Auditor")

    # 4. Invite the existing auditor (using different casing to test case-insensitivity)
    r = await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "NEW.test.auditor@auditor.com"}, headers=company_headers)
    assert r.status_code == 200

    # 5. Login as the auditor
    auditor_token = await get_auditor_token(client, email="new.test.auditor@auditor.com", password="testpass123")

    # 6. Check GET /auditor/engagements
    r = await client.get("/api/v1/auditor/engagements", headers={"Authorization": f"Bearer {auditor_token}"})
    assert r.status_code == 200
    engagements = r.json()
    assert len(engagements) >= 1
    # Find the one we just created
    eng = next((e for e in engagements if e["id"] == eng_id), None)
    assert eng is not None
    assert eng["status"] == "active" # Should be active since no acceptance was required

    # 7. Test inviting a NON-EXISTENT auditor
    r = await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "missing.auditor@auditor.com"}, headers=company_headers)
    assert r.status_code == 200

    # 8. Register the missing auditor
    await create_test_auditor(client, email="missing.auditor@auditor.com", password="testpass123", name="Missing Auditor")

    # 9. Login as the missing auditor
    missing_token = await get_auditor_token(client, email="missing.auditor@auditor.com", password="testpass123")

    # 10. Check GET /auditor/engagements for missing auditor
    r = await client.get("/api/v1/auditor/engagements", headers={"Authorization": f"Bearer {missing_token}"})
    assert r.status_code == 200
    missing_engagements = r.json()
    assert len(missing_engagements) == 1
    missing_eng = missing_engagements[0]
    assert missing_eng["status"] == "invited" # Should be invited because they were pending
