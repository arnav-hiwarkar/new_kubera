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
    await create_test_company(client, email="tb@a.com", password="pass1234")
    token = await get_company_token(client, email="tb@a.com", password="pass1234")
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
    await create_test_company(client, email="bad@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='bad@a.com', password='pass1234')}"}
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
    await create_test_company(client, email="re@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='re@a.com', password='pass1234')}"}
    eng_id = await make_engagement(client, headers)

    await import_tb(client, eng_id, headers)
    await import_tb(client, eng_id, headers)  # second import replaces, not appends
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/trial-balance", headers=headers)
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_engagement_starts_draft(client: AsyncClient):
    await create_test_company(client, email="dr@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='dr@a.com', password='pass1234')}"}
    resp = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == EngagementStatus.draft.value


@pytest.mark.asyncio
async def test_engagement_lifecycle(client: AsyncClient):
    await create_test_company(client, email="co@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co@a.com', password='pass1234')}"}

    await client.post("/api/v1/auth/auditor/register", json={"email": "aud@a.com", "password": "pass1234", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud@a.com", "password": "pass1234"})
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
    await create_test_company(client, email="del@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='del@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "deld@a.com", "password": "pass1234", "name": "A"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "deld@a.com", "password": "pass1234"})
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
    await create_test_company(client, email="pi@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='pi@a.com', password='pass1234')}"}
    eng_id = await make_engagement(client, co_headers)

    # Invite an email with no auditor account yet -> pending
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "future@aud.com"}, headers=co_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == EngagementStatus.invited.value
    assert resp.json()["auditor_grant_status"] == "pending"

    # Auditor registers with that email -> pending invite becomes a grant
    await client.post("/api/v1/auth/auditor/register", json={"email": "future@aud.com", "password": "pass1234", "name": "Future"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "future@aud.com", "password": "pass1234"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    resp = await client.get("/api/v1/auditor/engagements", headers=aud_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == eng_id


@pytest.mark.asyncio
async def test_reimport_blocked_after_entries(client: AsyncClient):
    await create_test_company(client, email="lock@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='lock@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "lockaud@a.com", "password": "pass1234", "name": "A"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "lockaud@a.com", "password": "pass1234"})
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


async def get_groups(client, headers):
    resp = await client.get("/api/v1/auditease/ledger-groups", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def find_group(groups, name):
    return next(g for g in groups if g["name"] == name)


@pytest.mark.asyncio
async def test_chart_of_accounts(client: AsyncClient):
    await create_test_company(client, email="coa2@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='coa2@a.com', password='pass1234')}"}

    groups = await get_groups(client, headers)
    tops = {g["name"] for g in groups if g["level"] == 0}
    assert tops == {"Assets", "Liabilities", "Income", "Expenditure"}
    assets = find_group(groups, "Assets")
    assert assets["company_id"] is None  # seeded, read-only

    # subgroup (level 1)
    resp = await client.post("/api/v1/auditease/ledger-groups", json={"name": "Current Assets", "parent_id": assets["id"]}, headers=headers)
    assert resp.status_code == 201, resp.text
    ca = resp.json()
    assert ca["level"] == 1

    # subsubgroup (level 2)
    resp = await client.post("/api/v1/auditease/ledger-groups", json={"name": "Cash & Bank", "parent_id": ca["id"]}, headers=headers)
    assert resp.status_code == 201
    cb = resp.json()
    assert cb["level"] == 2

    # depth cap
    resp = await client.post("/api/v1/auditease/ledger-groups", json={"name": "Too Deep", "parent_id": cb["id"]}, headers=headers)
    assert resp.status_code == 400

    # cannot rename a seeded top group
    resp = await client.patch(f"/api/v1/auditease/ledger-groups/{assets['id']}", json={"name": "Nope"}, headers=headers)
    assert resp.status_code == 403

    # can rename own group
    resp = await client.patch(f"/api/v1/auditease/ledger-groups/{ca['id']}", json={"name": "Current Assets 2"}, headers=headers)
    assert resp.status_code == 200

    # parent flags updated
    groups = await get_groups(client, headers)
    assert find_group(groups, "Assets")["has_children"] is True
    assert find_group(groups, "Current Assets 2")["has_children"] is True

    # delete guard: has children
    resp = await client.delete(f"/api/v1/auditease/ledger-groups/{ca['id']}", headers=headers)
    assert resp.status_code == 409
    # delete leaf, parent flag clears
    resp = await client.delete(f"/api/v1/auditease/ledger-groups/{cb['id']}", headers=headers)
    assert resp.status_code == 204
    groups = await get_groups(client, headers)
    assert find_group(groups, "Current Assets 2")["has_children"] is False


@pytest.mark.asyncio
async def test_ledger_mapping(client: AsyncClient):
    await create_test_company(client, email="map@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='map@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "mapaud@a.com", "password": "pass1234", "name": "A"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "mapaud@a.com", "password": "pass1234"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    eng_id = await make_engagement(client, co_headers)
    imp = await import_tb(client, eng_id, co_headers)
    ledgers = imp.json()["accounts"]
    cash, loan = ledgers[0]["id"], ledgers[1]["id"]

    groups = await get_groups(client, co_headers)
    assets = find_group(groups, "Assets")
    liab = find_group(groups, "Liabilities")

    # subgroup under Assets, then map cash to the leaf
    resp = await client.post("/api/v1/auditease/ledger-groups", json={"name": "Current Assets", "parent_id": assets["id"]}, headers=co_headers)
    ca = resp.json()

    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/ledgers/{cash}/map", json={"group_id": ca["id"]}, headers=co_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["mapped_group_path"] == ["Assets", "Current Assets"]

    # mapping to a non-leaf (Assets now has children) is rejected
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/ledgers/{loan}/map", json={"group_id": assets["id"]}, headers=co_headers)
    assert resp.status_code == 400

    # Liabilities is seeded with Schedule III sub-groups, so it is not a leaf and
    # cannot be mapped to directly.
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/ledgers/{loan}/map", json={"group_id": liab["id"]}, headers=co_headers)
    assert resp.status_code == 400

    # map loan to a company-created Liabilities leaf instead
    resp = await client.post("/api/v1/auditease/ledger-groups", json={"name": "Current Liabilities", "parent_id": liab["id"]}, headers=co_headers)
    cl = resp.json()
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/ledgers/{loan}/map", json={"group_id": cl["id"]}, headers=co_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["mapped_group_path"] == ["Liabilities", "Current Liabilities"]

    # can't add a subgroup under a leaf while a ledger is mapped directly to it
    resp = await client.post("/api/v1/auditease/ledger-groups", json={"name": "Provisions", "parent_id": cl["id"]}, headers=co_headers)
    assert resp.status_code == 409

    # company TB reflects the mapping path
    tb = await client.get(f"/api/v1/auditease/engagements/{eng_id}/trial-balance", headers=co_headers)
    cash_row = next(a for a in tb.json() if a["id"] == cash)
    assert cash_row["mapped_group_path"] == ["Assets", "Current Assets"]

    # auditor sees the mapping too
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "mapaud@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    tb = await client.get(f"/api/v1/auditor/engagements/{eng_id}/trial-balance", headers=aud_headers)
    cash_row = next(a for a in tb.json() if a["id"] == cash)
    assert cash_row["mapped_group_path"] == ["Assets", "Current Assets"]

    # bulk map then unmap
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/ledgers/bulk-map", json={"ledger_ids": [cash, loan], "group_id": ca["id"]}, headers=co_headers)
    assert resp.json()["updated"] == 2
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/ledgers/unmap", json={"ledger_ids": [cash, loan]}, headers=co_headers)
    assert resp.json()["updated"] == 2
    tb = await client.get(f"/api/v1/auditease/engagements/{eng_id}/trial-balance", headers=co_headers)
    assert all(a["mapped_group_path"] is None for a in tb.json())


@pytest.mark.asyncio
async def test_audit_entries(client: AsyncClient):
    await create_test_company(client, email="co2@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co2@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud2@a.com", "password": "pass1234", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud2@a.com", "password": "pass1234"})
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
    await create_test_company(client, email="co3@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co3@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud3@a.com", "password": "pass1234", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud3@a.com", "password": "pass1234"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    eng_id = await make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "aud3@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", json={"title": "Bank Statements", "description": "Provide bank statements"}, headers=aud_headers)
    assert resp.status_code == 200
    req_id = resp.json()["id"]

    files = {'file': ('test.txt', b'bank statements here', 'text/plain')}
    resp = await client.post("/api/v1/docvault/documents", data={'title': 'Bank Statements'}, files=files, headers=co_headers)
    doc_id = resp.json()["id"]

    resp = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/fulfill", json={"document_id": doc_id}, headers=co_headers)
    assert resp.status_code == 200

    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries", data={"initial_message": "What is this?"}, headers=aud_headers)
    assert resp.status_code == 200
    query_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/queries/{query_id}/messages", data={"text": "Here is the doc", "attached_document_id": doc_id}, headers=co_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auditease_cross_tenant_leak(client: AsyncClient):
    await create_test_company(client, email="coa@a.com", password="pass1234")
    headers_a = {"Authorization": f"Bearer {await get_company_token(client, email='coa@a.com', password='pass1234')}"}
    await create_test_company(client, email="cob@a.com", password="pass1234")
    headers_b = {"Authorization": f"Bearer {await get_company_token(client, email='cob@a.com', password='pass1234')}"}

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


@pytest.mark.asyncio
async def test_auditor_document_access_and_queries(client: AsyncClient):
    await create_test_company(client, email="co4@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co4@a.com', password='pass1234')}"}
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud4@a.com", "password": "pass1234", "name": "Auditor"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": "aud4@a.com", "password": "pass1234"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    
    # second auditor for cross-check
    await client.post("/api/v1/auth/auditor/register", json={"email": "aud_other@a.com", "password": "pass1234", "name": "Other"})
    resp2 = await client.post("/api/v1/auth/auditor/login", json={"email": "aud_other@a.com", "password": "pass1234"})
    aud_other_headers = {"Authorization": f"Bearer {resp2.json()['access_token']}"}

    eng_id = await make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": "aud4@a.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    
    # Auditor raises a query with a file
    files = {'file': ('query_doc.txt', b'query content', 'text/plain')}
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries", data={"initial_message": "Query 1"}, files=files, headers=aud_headers)
    assert resp.status_code == 200
    query_id = resp.json()["id"]
    q_msg = resp.json()["messages"][0]
    q_doc_id = q_msg["attached_document_id"]
    assert q_doc_id is not None
    
    # Auditor can download it
    resp = await client.get(f"/api/v1/auditor/documents/{q_doc_id}/download", headers=aud_headers)
    assert resp.status_code == 200
    assert resp.content == b'query content'
    
    # Other auditor cannot access it
    resp = await client.get(f"/api/v1/auditor/documents/{q_doc_id}/download", headers=aud_other_headers)
    assert resp.status_code == 404
    
    # Company responds with file
    c_files = {'file': ('reply_doc.txt', b'reply content', 'text/plain')}
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/queries/{query_id}/messages", data={"text": "Here is reply"}, files=c_files, headers=co_headers)
    assert resp.status_code == 200
    c_doc_id = resp.json()["attached_document_id"]
    
    # Auditor can download reply file
    resp = await client.get(f"/api/v1/auditor/documents/{c_doc_id}/download", headers=aud_headers)
    assert resp.status_code == 200
    assert resp.content == b'reply content'
    
    # Auditor lists queries
    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/queries", headers=aud_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    
    # Auditor closes query
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries/{query_id}/close", headers=aud_headers)
    assert resp.status_code == 200
    
    # Can no longer add messages
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries/{query_id}/messages", data={"text": "late"}, headers=aud_headers)
    assert resp.status_code == 400
    
    # Company closes engagement
    await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=co_headers)
    
    # Auditor can no longer download documents
    resp = await client.get(f"/api/v1/auditor/documents/{c_doc_id}/download", headers=aud_headers)
    assert resp.status_code == 404


# --- Entry ledger names + report preview ---------------------------------------

async def _accept_auditor(client, co_headers, eng_id, email):
    await client.post("/api/v1/auth/auditor/register", json={"email": email, "password": "pass1234", "name": "A"})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": email, "password": "pass1234"})
    aud_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/invite-auditor", json={"email": email}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    return aud_headers


@pytest.mark.asyncio
async def test_entry_lines_include_ledger_name(client: AsyncClient):
    """Both the auditor and company entry views must carry the ledger name/code so
    the UI never shows 'Unknown Ledger'."""
    await create_test_company(client, email="eln@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='eln@a.com', password='pass1234')}"}
    eng_id = await make_engagement(client, co_headers)
    imp = await import_tb(client, eng_id, co_headers)
    ledgers = {a["ledger_name"]: a for a in imp.json()["accounts"]}
    cash, loan = ledgers["Cash"], ledgers["Loan"]
    aud_headers = await _accept_auditor(client, co_headers, eng_id, "elnaud@a.com")

    entry = {
        "code": "AJE-1",
        "description": "Reclass",
        "lines": [
            {"ledger_id": cash["id"], "side": "debit", "amount": 100},
            {"ledger_id": loan["id"], "side": "credit", "amount": 100},
        ],
    }
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/entries", json=entry, headers=aud_headers)
    assert resp.status_code == 201, resp.text
    # The create response already carries ledger identity.
    created_lines = {l["ledger_id"]: l for l in resp.json()["lines"]}
    assert created_lines[cash["id"]]["ledger_name"] == "Cash"
    assert created_lines[cash["id"]]["ledger_code"] == "A1"
    entry_id = resp.json()["id"]

    # Auditor list view
    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/entries", headers=aud_headers)
    aud_lines = {l["ledger_id"]: l for l in resp.json()[0]["lines"]}
    assert aud_lines[cash["id"]]["ledger_name"] == "Cash"
    assert aud_lines[loan["id"]]["ledger_name"] == "Loan"

    # Company list view
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/entries", headers=co_headers)
    co_lines = {l["ledger_id"]: l for l in resp.json()[0]["lines"]}
    assert co_lines[cash["id"]]["ledger_name"] == "Cash"
    assert co_lines[loan["id"]]["ledger_name"] == "Loan"

    # Approve response also carries ledger identity
    resp = await client.patch(f"/api/v1/auditease/entries/{entry_id}/approve", json={"status": "approved"}, headers=co_headers)
    assert resp.status_code == 200
    ap_lines = {l["ledger_id"]: l for l in resp.json()["lines"]}
    assert ap_lines[loan["id"]]["ledger_name"] == "Loan"


@pytest.mark.asyncio
async def test_delete_closed_engagement_with_children(client: AsyncClient):
    """A closed engagement that accumulated entries, a query and a requirement must
    still delete cleanly (regression: FK 500 when children weren't cascaded)."""
    await create_test_company(client, email="delc@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='delc@a.com', password='pass1234')}"}
    eng_id = await make_engagement(client, co_headers)
    imp = await import_tb(client, eng_id, co_headers)
    ledgers = imp.json()["accounts"]
    aud_headers = await _accept_auditor(client, co_headers, eng_id, "delcaud@a.com")

    # Auditor adds an entry, a requirement and a query (the previously-uncascaded rows).
    await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/entries",
        json={"description": "Adj", "lines": [
            {"ledger_id": ledgers[0]["id"], "side": "debit", "amount": 100},
            {"ledger_id": ledgers[1]["id"], "side": "credit", "amount": 100},
        ]},
        headers=aud_headers,
    )
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", json={"description": "docs"}, headers=aud_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries", data={"initial_message": "hi"}, headers=aud_headers)

    # Close, then delete — must succeed, not 500.
    await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=co_headers)
    resp = await client.delete(f"/api/v1/auditease/engagements/{eng_id}", headers=co_headers)
    assert resp.status_code == 204, resp.text

    # Gone.
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}", headers=co_headers)
    assert resp.status_code == 404


REPORT_CSV = (
    b"Code,Name,Opening,Debit,Credit,Closing\n"
    b"A1,Cash,0,0,0,1000\n"
    b"L1,Loan,0,0,0,600\n"
    b"I1,Sales,0,0,0,500\n"
    b"E1,Rent,0,0,0,100\n"
    b"U1,Suspense,0,0,0,999\n"
)


# Same figures as REPORT_CSV but in the standard SIGNED trial-balance convention:
# credit-natured accounts (Income, Liabilities) carry a negative closing balance.
SIGNED_REPORT_CSV = (
    b"Code,Name,Opening,Debit,Credit,Closing\n"
    b"A1,Cash,0,0,0,1000\n"
    b"L1,Loan,0,0,600,-600\n"
    b"I1,Sales,0,0,500,-500\n"
    b"E1,Rent,0,100,0,100\n"
)

# Signed convention where expenditure exceeds income -> a genuine net LOSS.
SIGNED_LOSS_CSV = (
    b"Code,Name,Opening,Debit,Credit,Closing\n"
    b"A1,Cash,0,0,0,1000\n"
    b"L1,Loan,0,0,900,-900\n"
    b"I1,Sales,0,0,100,-100\n"
    b"E1,Rent,0,500,0,500\n"
)


async def _map_pl_ledgers(client, eng_id, co_headers, ledgers):
    """Map Cash/Loan/Sales/Rent to the seeded Schedule III leaves (shared setup)."""
    groups = await get_groups(client, co_headers)

    async def map_to(ledger_name, group_name):
        gid = find_group(groups, group_name)["id"]
        lid = ledgers[ledger_name]["id"]
        r = await client.post(
            f"/api/v1/auditease/engagements/{eng_id}/ledgers/{lid}/map",
            json={"group_id": gid}, headers=co_headers,
        )
        assert r.status_code == 200, r.text

    await map_to("Cash", "Cash and Cash Equivalents")
    await map_to("Loan", "Trade Payables")
    await map_to("Sales", "Revenue from Operations")
    await map_to("Rent", "Other Expenses")


@pytest.mark.asyncio
async def test_report_preview_signed_trial_balance(client: AsyncClient):
    """Regression: a signed trial balance (credit accounts negative) must still yield
    net profit = Income - Expenditure, not -(|Income| + |Expenditure|). Previously the
    negative Income flipped the subtraction into an addition and reported a false loss."""
    await create_test_company(client, email="signed@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='signed@a.com', password='pass1234')}"}
    eng_id = await make_engagement(client, co_headers)
    imp = await import_tb(client, eng_id, co_headers, csv=SIGNED_REPORT_CSV)
    ledgers = {a["ledger_name"]: a for a in imp.json()["accounts"]}
    await _map_pl_ledgers(client, eng_id, co_headers, ledgers)

    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/reports/preview", headers=co_headers)
    assert resp.status_code == 200, resp.text
    p = resp.json()
    # Totals are reported as positive natural-side magnitudes despite the negative source.
    assert p["totals"] == {"assets": 1000.0, "liabilities": 600.0, "income": 500.0, "expenditure": 100.0}
    # The net is the difference (500 - 100 = 400 profit) — NOT the -600 sum-of-magnitudes.
    assert p["net_profit"] == 400.0
    # And the balance sheet reconciles (Liabilities is also normalized to a magnitude).
    assert p["balance_check"]["liabilities_plus_equity"] == 1000.0
    assert p["balance_check"]["balanced"] is True


@pytest.mark.asyncio
async def test_report_preview_signed_net_loss(client: AsyncClient):
    """A signed trial balance where Expenditure > Income reports a real net LOSS
    (negative net_profit), confirming the sign is genuine and not a flip artifact."""
    await create_test_company(client, email="loss@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='loss@a.com', password='pass1234')}"}
    eng_id = await make_engagement(client, co_headers)
    imp = await import_tb(client, eng_id, co_headers, csv=SIGNED_LOSS_CSV)
    ledgers = {a["ledger_name"]: a for a in imp.json()["accounts"]}
    await _map_pl_ledgers(client, eng_id, co_headers, ledgers)

    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/reports/preview", headers=co_headers)
    assert resp.status_code == 200, resp.text
    p = resp.json()
    assert p["totals"]["income"] == 100.0
    assert p["totals"]["expenditure"] == 500.0
    # Income 100 - Expenditure 500 = -400 (a real loss), not +600 or -600.
    assert p["net_profit"] == -400.0


@pytest.mark.asyncio
async def test_report_preview(client: AsyncClient):
    await create_test_company(client, email="rep@a.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='rep@a.com', password='pass1234')}"}
    eng_id = await make_engagement(client, co_headers)
    imp = await import_tb(client, eng_id, co_headers, csv=REPORT_CSV)
    ledgers = {a["ledger_name"]: a for a in imp.json()["accounts"]}

    groups = await get_groups(client, co_headers)

    async def map_to(ledger_name, group_name):
        gid = find_group(groups, group_name)["id"]
        lid = ledgers[ledger_name]["id"]
        r = await client.post(
            f"/api/v1/auditease/engagements/{eng_id}/ledgers/{lid}/map",
            json={"group_id": gid}, headers=co_headers,
        )
        assert r.status_code == 200, r.text

    # Map four ledgers to seeded Schedule III leaves; leave Suspense unmapped.
    await map_to("Cash", "Cash and Cash Equivalents")
    await map_to("Loan", "Trade Payables")
    await map_to("Sales", "Revenue from Operations")
    await map_to("Rent", "Other Expenses")

    # --- Preview before any entries -------------------------------------------
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/reports/preview", headers=co_headers)
    assert resp.status_code == 200, resp.text
    p = resp.json()
    assert p["totals"] == {"assets": 1000.0, "liabilities": 600.0, "income": 500.0, "expenditure": 100.0}
    assert p["net_profit"] == 400.0
    assert p["balance_check"]["liabilities_plus_equity"] == 1000.0
    assert p["balance_check"]["balanced"] is True
    assert p["unmapped_count"] == 1
    assert p["entries"]["approved_count"] == 0
    assert p["entries"]["proposed_count"] == 0

    # --- Add + approve an adjusting entry -------------------------------------
    aud_headers = await _accept_auditor(client, co_headers, eng_id, "repaud@a.com")
    entry = {
        "description": "Extra sale",
        "lines": [
            {"ledger_id": ledgers["Cash"]["id"], "side": "debit", "amount": 200},
            {"ledger_id": ledgers["Sales"]["id"], "side": "credit", "amount": 200},
        ],
    }
    resp = await client.post(f"/api/v1/auditor/engagements/{eng_id}/entries", json=entry, headers=aud_headers)
    entry_id = resp.json()["id"]
    await client.patch(f"/api/v1/auditease/entries/{entry_id}/approve", json={"status": "approved"}, headers=co_headers)

    # Second, un-approved entry -> counted as proposed only
    entry2 = {
        "description": "Pending",
        "lines": [
            {"ledger_id": ledgers["Rent"]["id"], "side": "debit", "amount": 50},
            {"ledger_id": ledgers["Loan"]["id"], "side": "credit", "amount": 50},
        ],
    }
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/entries", json=entry2, headers=aud_headers)

    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/reports/preview", headers=co_headers)
    p = resp.json()
    # Approved debit to Cash raises assets; credit to Sales raises income.
    assert p["totals"]["assets"] == 1200.0
    assert p["totals"]["income"] == 700.0
    assert p["net_profit"] == 600.0
    assert p["balance_check"]["balanced"] is True  # double-entry keeps it balanced
    assert p["entries"]["approved_count"] == 1
    assert p["entries"]["proposed_count"] == 1

    cash_line = next(l for l in p["lines"] if l["ledger_name"] == "Cash")
    assert cash_line["adjustment"] == 200.0
    assert cash_line["final"] == 1200.0
    assert cash_line["top_group"] == "Assets"

    # --- Generate persists an HTML report to docVault --------------------------
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/reports/generate", headers=co_headers)
    assert resp.status_code == 200, resp.text
    assert "id" in resp.json() and "url" in resp.json()


# --- Report HTML rendering (Profit & Loss must be a difference, never a sum) ----

import uuid as _uuid

from app.routers.auditease import _report_to_html
from app.schemas.auditease import (
    ReportLine, ReportTotals, ReportBalanceCheck, ReportEntriesBlock,
    ReportPreviewResponse,
)


def _make_report(*, income: float, expenditure: float) -> ReportPreviewResponse:
    """A minimal P&L-focused report with one Income and one Expenditure ledger.

    Balances are stored as absolute (positive) values, mirroring how AuditEase
    persists them, so an accidental sum is easy to distinguish from the difference.
    """
    net = income - expenditure
    return ReportPreviewResponse(
        period_label="FY24",
        lines=[
            ReportLine(
                ledger_id=_uuid.uuid4(), ledger_name="Sales", ledger_code="I1",
                top_group="Income", group_path=["Income", "Revenue from Operations"],
                closing=income, adjustment=0.0, final=income,
            ),
            ReportLine(
                ledger_id=_uuid.uuid4(), ledger_name="Rent", ledger_code="E1",
                top_group="Expenditure", group_path=["Expenditure", "Other Expenses"],
                closing=expenditure, adjustment=0.0, final=expenditure,
            ),
        ],
        totals=ReportTotals(assets=0.0, liabilities=0.0, income=income, expenditure=expenditure),
        net_profit=net,
        balance_check=ReportBalanceCheck(
            assets=0.0, liabilities_plus_equity=net, difference=-net, balanced=False,
        ),
        entries=ReportEntriesBlock(approved=[], approved_count=0, proposed_count=0),
        unmapped_count=0,
    )


def test_report_html_pl_net_is_difference_not_sum():
    """Regression: the P&L bottom line must be Income - Expenditure, and Income and
    Expenditure must render as separate sections so no combined section lumps their
    absolute balances into a meaningless sum."""
    html = _report_to_html(_make_report(income=700.0, expenditure=100.0))

    # Net is the difference (600.00), labelled Profit because it is positive.
    assert "Net Profit: 600.00" in html
    # The misleading sum (700 + 100 = 800) must never surface as the net.
    assert "Net Profit: 800.00" not in html
    assert "Net Loss" not in html

    # Income and Expenditure are separated into their own sections (like the
    # Assets / Liabilities split), not merged under one "Profit & Loss" data block.
    assert "<h2>Income</h2>" in html
    assert "<h2>Expenditure</h2>" in html

    # The correctly computed component totals are still reported.
    assert "Total Income: 700.00" in html
    assert "Total Expenditure: 100.00" in html


def test_report_html_pl_reports_a_loss():
    """When Expenditure exceeds Income the report shows a Net Loss of the difference."""
    html = _report_to_html(_make_report(income=100.0, expenditure=700.0))
    assert "Net Loss: 600.00" in html
    assert "Net Profit" not in html
    # Not the sum (800) under either label.
    assert "800.00" not in html
