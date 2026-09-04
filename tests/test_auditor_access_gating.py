import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token, create_test_auditor
from tests.test_auditease import make_engagement, import_tb


@pytest.mark.asyncio
async def test_unaccepted_auditor_cannot_access_workspace_data(client: AsyncClient):
    """An auditor with status 'invited' (not yet accepted) must be blocked
    from reading trial balance, entries, requirements, queries, and documents."""
    # 1. Setup company and engagement
    await create_test_company(client, email="gateco@test.com", password="Valid1!Pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='gateco@test.com', password='Valid1!Pass')}"}
    eng_id = await make_engagement(client, co_headers)
    await import_tb(client, eng_id, co_headers)

    # 2. Setup Lead Auditor who accepts and creates a query with an attached document
    lead_email = "lead@firm.com"
    await create_test_auditor(client, email=lead_email, password="Valid1!Pass", name="Lead Auditor")
    resp_lead = await client.post("/api/v1/auth/auditor/login", json={"email": lead_email, "password": "Valid1!Pass"})
    lead_headers = {"Authorization": f"Bearer {resp_lead.json()['access_token']}"}

    # Invite and accept Lead Auditor
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": lead_email}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=lead_headers)

    # Lead auditor creates a query with attached file
    q_res = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/queries",
        data={"initial_message": "Please review"},
        files={"file": ("evidence.txt", b"confidential evidence", "text/plain")},
        headers=lead_headers,
    )
    assert q_res.status_code == 200, q_res.text
    q_doc_id = q_res.json()["messages"][0]["attached_document_id"]
    assert q_doc_id is not None

    # Lead auditor creates a requirement request
    req_res = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"title": "Bank Statements", "description": "FY bank statements"},
        headers=lead_headers,
    )
    assert req_res.status_code == 200, req_res.text

    # 3. New auditor registers and gets invited (status 'invited')
    aud_email = "gatedauditor@firm.com"
    await create_test_auditor(client, email=aud_email, password="Valid1!Pass", name="Gated Auditor")
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": aud_email, "password": "Valid1!Pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    # Send invite to auditor (creates AuditorEngagementGrant with status='invited')
    inv_res = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": aud_email},
        headers=co_headers,
    )
    assert inv_res.status_code == 200

    # 4. Auditor can list engagements and sees status 'invited'
    list_res = await client.get("/api/v1/auditor/engagements", headers=aud_headers)
    assert list_res.status_code == 200
    engs = list_res.json()
    assert len(engs) == 1
    assert engs[0]["id"] == eng_id
    assert engs[0]["status"] == "invited"

    # 5. Auditor is blocked (403) from workspace data endpoints before accept
    tb_res = await client.get(f"/api/v1/auditor/engagements/{eng_id}/trial-balance", headers=aud_headers)
    assert tb_res.status_code == 403, f"Expected 403 for unaccepted TB access, got {tb_res.status_code}"

    entries_res = await client.get(f"/api/v1/auditor/engagements/{eng_id}/entries", headers=aud_headers)
    assert entries_res.status_code == 403, f"Expected 403 for unaccepted entries access, got {entries_res.status_code}"

    reqs_res = await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", headers=aud_headers)
    assert reqs_res.status_code == 403, f"Expected 403 for unaccepted requirements access, got {reqs_res.status_code}"

    queries_res = await client.get(f"/api/v1/auditor/engagements/{eng_id}/queries", headers=aud_headers)
    assert queries_res.status_code == 403, f"Expected 403 for unaccepted queries access, got {queries_res.status_code}"

    doc_res = await client.get(f"/api/v1/auditor/documents/{q_doc_id}/download", headers=aud_headers)
    assert doc_res.status_code in (403, 404), f"Expected 403/404 for unaccepted doc download, got {doc_res.status_code}"

    # 6. Auditor accepts the engagement
    accept_res = await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    assert accept_res.status_code == 200
    assert accept_res.json()["message"] == "Engagement accepted"

    # 7. After accept, workspace data endpoints succeed
    list_res_after = await client.get("/api/v1/auditor/engagements", headers=aud_headers)
    assert list_res_after.status_code == 200
    assert list_res_after.json()[0]["status"] == "active"

    tb_res_after = await client.get(f"/api/v1/auditor/engagements/{eng_id}/trial-balance", headers=aud_headers)
    assert tb_res_after.status_code == 200

    entries_res_after = await client.get(f"/api/v1/auditor/engagements/{eng_id}/entries", headers=aud_headers)
    assert entries_res_after.status_code == 200

    reqs_res_after = await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", headers=aud_headers)
    assert reqs_res_after.status_code == 200

    queries_res_after = await client.get(f"/api/v1/auditor/engagements/{eng_id}/queries", headers=aud_headers)
    assert queries_res_after.status_code == 200

    doc_res_after = await client.get(f"/api/v1/auditor/documents/{q_doc_id}/download", headers=aud_headers)
    assert doc_res_after.status_code == 200
    assert doc_res_after.content == b"confidential evidence"
