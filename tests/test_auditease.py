import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token
from app.models.auditease import EngagementStatus, GrantStatus, AuditEntryStatus, RequestStatus, QueryStatus

@pytest.mark.asyncio
async def test_trial_balance_import(client: AsyncClient):
    await create_test_company(client, email="tb@a.com", password="pass")
    token = await get_company_token(client, email="tb@a.com", password="pass")
    headers = {"Authorization": f"Bearer {token}"}

    rows = [
        {"ledger_code": "A1", "ledger_name": "Cash", "opening_balance": 100, "debit": 50, "credit": 0, "closing_balance": 150},
        {"ledger_code": "L1", "ledger_name": "Loan", "opening_balance": -100, "debit": 0, "credit": 50, "closing_balance": -150}
    ]
    
    resp = await client.post("/api/v1/auditease/trial-balance/import", json=rows, headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    
    resp = await client.get("/api/v1/auditease/trial-balance", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_engagement_lifecycle(client: AsyncClient):
    # Company Setup
    await create_test_company(client, email="co@a.com", password="pass")
    co_token = await get_company_token(client, email="co@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {co_token}"}
    
    # Auditor Setup
    resp = await client.post("/api/v1/auth/auditor/register", json={"email": "aud@a.com", "password": "pass", "name": "Auditor"})
    assert resp.status_code == 201
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud@a.com", "password": "pass"})
    aud_token = resp.json()["access_token"]
    aud_headers = {"Authorization": f"Bearer {aud_token}"}
    
    # 1. Company creates engagement
    resp = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY2023"}, headers=co_headers)
    assert resp.status_code == 201
    eng_id = resp.json()["id"]
    
    # 2. Company invites auditor
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "aud@a.com"}, headers=co_headers)
    assert resp.status_code == 200
    
    # 3. Auditor sees invite and accepts
    resp = await client.get("/api/v1/auditor/engagements", headers=aud_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    assert resp.status_code == 200
    
    # 4. Company closes engagement
    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=co_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == EngagementStatus.closed
    
    # 5. Auditor loses access
    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/trial-balance", headers=aud_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_entries(client: AsyncClient):
    # Setup
    await create_test_company(client, email="co2@a.com", password="pass")
    co_token = await get_company_token(client, email="co2@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {co_token}"}
    
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud2@a.com", "password": "pass", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud2@a.com", "password": "pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    
    # TB and Engagement
    resp = await client.post("/api/v1/auditease/trial-balance/import", json=[
        {"ledger_code": "1", "ledger_name": "Acc1"}
    ], headers=co_headers)
    ledger_id = resp.json()[0]["id"]
    
    resp = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co_headers)
    eng_id = resp.json()["id"]
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "aud2@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    
    # Auditor proposes entry
    entry_data = {
        "description": "Adjusting entry",
        "lines": [
            {"ledger_id": ledger_id, "side": "debit", "amount": 100},
            {"ledger_id": ledger_id, "side": "credit", "amount": 100} # same ledger just for testing balance
        ]
    }
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/entries", json=entry_data, headers=aud_headers)
    assert resp.status_code == 201
    entry_id = resp.json()["id"]
    
    # Company approves
    resp = await client.patch(f"/api/v1/auditease/entries/{entry_id}/approve", json={"status": "approved"}, headers=co_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_requirements_and_queries(client: AsyncClient):
    # Setup
    await create_test_company(client, email="co3@a.com", password="pass")
    co_token = await get_company_token(client, email="co3@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {co_token}"}
    
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud3@a.com", "password": "pass", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud3@a.com", "password": "pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    
    resp = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co_headers)
    eng_id = resp.json()["id"]
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "aud3@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    
    # Auditor creates requirement
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", json={"description": "Provide bank statements"}, headers=aud_headers)
    assert resp.status_code == 200
    req_id = resp.json()["id"]
    
    # Company uploads document to docvault
    files = {'file': ('test.txt', b'bank statements here', 'text/plain')}
    resp = await client.post("/api/v1/docvault/documents", data={'title': 'Bank Statements'}, files=files, headers=co_headers)
    doc_id = resp.json()["id"]
    
    # Company fulfills requirement
    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/fulfill", json={"document_id": doc_id}, headers=co_headers)
    assert resp.status_code == 200
    
    # Auditor creates query
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries", json={"initial_message": "What is this?"}, headers=aud_headers)
    assert resp.status_code == 200
    query_id = resp.json()["id"]
    
    # Company replies with doc
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/queries/{query_id}/messages", json={"text": "Here is the doc", "attached_document_id": doc_id}, headers=co_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auditease_cross_tenant_leak(client: AsyncClient):
    # A
    await create_test_company(client, email="coa@a.com", password="pass")
    token_a = await get_company_token(client, email="coa@a.com", password="pass")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    
    # B
    await create_test_company(client, email="cob@a.com", password="pass")
    token_b = await get_company_token(client, email="cob@a.com", password="pass")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    # A creates TB and Engagement
    await client.post("/api/v1/auditease/trial-balance/import", json=[{"ledger_code": "1", "ledger_name": "A's Ledger"}], headers=headers_a)
    resp = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=headers_a)
    eng_id = resp.json()["id"]
    
    # B cannot see A's TB
    resp = await client.get("/api/v1/auditease/trial-balance", headers=headers_b)
    assert len(resp.json()) == 0
    
    # B cannot see A's Engagements
    resp = await client.get("/api/v1/auditease/engagements", headers=headers_b)
    assert len(resp.json()) == 0
    
    # B cannot close A's engagement
    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=headers_b)
    assert resp.status_code == 404
