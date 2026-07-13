import json

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token
from app.models.auditease import EngagementStatus, GrantStatus, AuditEntryStatus, RequestStatus, QueryStatus

# --- Trial-balance import fixtures/helpers -------------------------------------

TB_CSV = (
    b"Code,Name,Opening,Debit,Credit,Closing\n"
    b"A1,Cash,100,50,0,150\n"
    b"L1,Loan,-100,0,50,-150\n"
)
TB_MAP = {
    "ledger_code": "Code",
    "ledger_name": "Name",
    "opening_balance": "Opening",
    "debit": "Debit",
    "credit": "Credit",
    "closing_balance": "Closing",
}


async def make_engagement(client, headers, label="FY24"):
    resp = await client.post("/api/v1/auditease/engagements", json={"period_label": label}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def import_tb(client, eng_id, headers, csv=TB_CSV, cmap=TB_MAP, sheet=None):
    data = {"column_map": json.dumps(cmap)}
    if sheet is not None:
        data["sheet"] = sheet
    return await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/trial-balance/import",
        data=data,
        files={"file": ("tb.csv", csv, "text/csv")},
        headers=headers,
    )


# --- Tests ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trial_balance_import_flow(client: AsyncClient):
    await create_test_company(client, email="tb@a.com", password="pass")
    token = await get_company_token(client, email="tb@a.com", password="pass")
    headers = {"Authorization": f"Bearer {token}"}

    eng_id = await make_engagement(client, headers)

    # Step 1: inspect returns sheet headers + preview
    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/trial-balance/inspect",
        files={"file": ("tb.csv", TB_CSV, "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    sheets = resp.json()["sheets"]
    assert sheets[0]["headers"] == ["Code", "Name", "Opening", "Debit", "Credit", "Closing"]
    assert len(sheets[0]["preview_rows"]) == 2

    # Step 2: import with column map
    resp = await import_tb(client, eng_id, headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 2
    assert body["skipped"] == 0
    assert body["balanced"] is True  # debit 50 == credit 50

    # View the per-engagement TB
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/trial-balance", headers=headers)
    assert resp.status_code == 200
    accounts = resp.json()
    assert len(accounts) == 2
    assert all(a["engagement_id"] == eng_id for a in accounts)


@pytest.mark.asyncio
async def test_tb_import_skips_bad_rows(client: AsyncClient):
    await create_test_company(client, email="bad@a.com", password="pass")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='bad@a.com', password='pass')}"}
    eng_id = await make_engagement(client, headers)

    csv = (
        b"Code,Name,Opening,Debit,Credit,Closing\n"
        b"A1,Cash,100,50,0,150\n"
        b"B2,Bad,100,notanumber,0,150\n"   # non-numeric debit -> skipped
        b",,,,,\n"                          # fully blank -> ignored
    )
    resp = await import_tb(client, eng_id, headers, csv=csv)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1
    assert body["errors"][0]["row"] == 2


@pytest.mark.asyncio
async def test_tb_reimport_replaces(client: AsyncClient):
    await create_test_company(client, email="re@a.com", password="pass")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='re@a.com', password='pass')}"}
    eng_id = await make_engagement(client, headers)

    await import_tb(client, eng_id, headers)
    await import_tb(client, eng_id, headers)  # second import replaces, not appends
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/trial-balance", headers=headers)
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_engagement_starts_draft(client: AsyncClient):
    await create_test_company(client, email="dr@a.com", password="pass")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='dr@a.com', password='pass')}"}
    resp = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == EngagementStatus.draft.value


@pytest.mark.asyncio
async def test_engagement_lifecycle(client: AsyncClient):
    await create_test_company(client, email="co@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co@a.com', password='pass')}"}

    await client.post("/api/v1/auth/auditor/register", json={"email": "aud@a.com", "password": "pass", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud@a.com", "password": "pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    eng_id = await make_engagement(client, co_headers)

    # Invite moves draft -> invited
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "aud@a.com"}, headers=co_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == EngagementStatus.invited.value
    assert resp.json()["auditor_email"] == "aud@a.com"
    assert resp.json()["auditor_grant_status"] == GrantStatus.invited.value

    # Auditor sees the invite
    resp = await client.get("/api/v1/auditor/engagements", headers=aud_headers)
    assert len(resp.json()) == 1

    # Accept moves invited -> active
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    assert resp.status_code == 200
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}", headers=co_headers)
    assert resp.json()["status"] == EngagementStatus.active.value

    # Close -> closed, auditor loses access + engagement vanishes from their list
    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=co_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == EngagementStatus.closed.value

    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/trial-balance", headers=aud_headers)
    assert resp.status_code == 403
    resp = await client.get("/api/v1/auditor/engagements", headers=aud_headers)
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_engagement_guard(client: AsyncClient):
    await create_test_company(client, email="del@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='del@a.com', password='pass')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "deld@a.com", "password": "pass", "name": "A"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "deld@a.com", "password": "pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    # Draft engagement can be deleted
    eng_id = await make_engagement(client, co_headers)
    resp = await client.delete(f"/api/v1/auditease/engagements/{eng_id}", headers=co_headers)
    assert resp.status_code == 204

    # Active engagement cannot be deleted
    eng2 = await make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng2}/invite-auditor", json={"email": "deld@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng2}/accept", headers=aud_headers)
    resp = await client.delete(f"/api/v1/auditease/engagements/{eng2}", headers=co_headers)
    assert resp.status_code == 409

    # But once closed, cleanup delete is allowed
    await client.patch(f"/api/v1/auditease/engagements/{eng2}/close", headers=co_headers)
    resp = await client.delete(f"/api/v1/auditease/engagements/{eng2}", headers=co_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_pending_invite_autoconverts_on_registration(client: AsyncClient):
    await create_test_company(client, email="pi@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='pi@a.com', password='pass')}"}
    eng_id = await make_engagement(client, co_headers)

    # Invite an email with no auditor account yet -> pending
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "future@aud.com"}, headers=co_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == EngagementStatus.invited.value
    assert resp.json()["auditor_grant_status"] == "pending"

    # Auditor registers with that email -> pending invite becomes a grant
    await client.post("/api/v1/auth/auditor/register", json={"email": "future@aud.com", "password": "pass", "name": "Future"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "future@aud.com", "password": "pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    resp = await client.get("/api/v1/auditor/engagements", headers=aud_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == eng_id


@pytest.mark.asyncio
async def test_reimport_blocked_after_entries(client: AsyncClient):
    await create_test_company(client, email="lock@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='lock@a.com', password='pass')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "lockaud@a.com", "password": "pass", "name": "A"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "lockaud@a.com", "password": "pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    eng_id = await make_engagement(client, co_headers)
    resp = await import_tb(client, eng_id, co_headers)
    ledgers = resp.json()["accounts"]
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "lockaud@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    entry = {
        "description": "Adj",
        "lines": [
            {"ledger_id": ledgers[0]["id"], "side": "debit", "amount": 100},
            {"ledger_id": ledgers[1]["id"], "side": "credit", "amount": 100},
        ],
    }
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/entries", json=entry, headers=aud_headers)
    assert resp.status_code == 201, resp.text

    # Re-import now blocked
    resp = await import_tb(client, eng_id, co_headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_audit_entries(client: AsyncClient):
    await create_test_company(client, email="co2@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co2@a.com', password='pass')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud2@a.com", "password": "pass", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud2@a.com", "password": "pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    eng_id = await make_engagement(client, co_headers)
    resp = await import_tb(client, eng_id, co_headers)
    ledgers = resp.json()["accounts"]
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "aud2@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    entry_data = {
        "description": "Adjusting entry",
        "lines": [
            {"ledger_id": ledgers[0]["id"], "side": "debit", "amount": 100},
            {"ledger_id": ledgers[1]["id"], "side": "credit", "amount": 100},
        ],
    }
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/entries", json=entry_data, headers=aud_headers)
    assert resp.status_code == 201, resp.text
    entry_id = resp.json()["id"]

    resp = await client.patch(f"/api/v1/auditease/entries/{entry_id}/approve", json={"status": "approved"}, headers=co_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_requirements_and_queries(client: AsyncClient):
    await create_test_company(client, email="co3@a.com", password="pass")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co3@a.com', password='pass')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud3@a.com", "password": "pass", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud3@a.com", "password": "pass"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    eng_id = await make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "aud3@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", json={"description": "Provide bank statements"}, headers=aud_headers)
    assert resp.status_code == 200
    req_id = resp.json()["id"]

    files = {'file': ('test.txt', b'bank statements here', 'text/plain')}
    resp = await client.post("/api/v1/docvault/documents", data={'title': 'Bank Statements'}, files=files, headers=co_headers)
    doc_id = resp.json()["id"]

    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/fulfill", json={"document_id": doc_id}, headers=co_headers)
    assert resp.status_code == 200

    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries", json={"initial_message": "What is this?"}, headers=aud_headers)
    assert resp.status_code == 200
    query_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/queries/{query_id}/messages", json={"text": "Here is the doc", "attached_document_id": doc_id}, headers=co_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auditease_cross_tenant_leak(client: AsyncClient):
    await create_test_company(client, email="coa@a.com", password="pass")
    headers_a = {"Authorization": f"Bearer {await get_company_token(client, email='coa@a.com', password='pass')}"}
    await create_test_company(client, email="cob@a.com", password="pass")
    headers_b = {"Authorization": f"Bearer {await get_company_token(client, email='cob@a.com', password='pass')}"}

    eng_id = await make_engagement(client, headers_a)
    await import_tb(client, eng_id, headers_a)

    # B cannot read A's engagement TB
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/trial-balance", headers=headers_b)
    assert resp.status_code == 404

    # B cannot see A's engagements
    resp = await client.get("/api/v1/auditease/engagements", headers=headers_b)
    assert len(resp.json()) == 0

    # B cannot close A's engagement
    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=headers_b)
    assert resp.status_code == 404
