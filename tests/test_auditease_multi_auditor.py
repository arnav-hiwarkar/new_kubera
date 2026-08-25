import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token


async def _register_login(client: AsyncClient, email: str) -> dict:
    await client.post("/api/v1/auth/auditor/register", json={"email": email, "password": "pass1234", "name": email.split("@")[0].title()})
    resp = await client.post("/api/v1/auth/auditor/login", json={"email": email, "password": "pass1234"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _make_user(client: AsyncClient, admin_headers: dict, email: str, role: str) -> dict:
    resp = await client.post("/api/v1/users", json={
        "email": email, "password": "pass1234",
        "full_name": email.split("@")[0], "role": role,
    }, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_two_auditors_coexist(client: AsyncClient):
    await create_test_company(client, email="ma@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="ma@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _register_login(client, "one@a.com")
    await _register_login(client, "two@a.com")

    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "one@a.com"}, headers=co)
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "two@a.com"}, headers=co)
    assert resp.status_code == 200, resp.text

    auds = resp.json()["auditors"]
    assert len(auds) == 2
    assert {a["email"] for a in auds} == {"one@a.com", "two@a.com"}
    assert all(a["status"] == "invited" for a in auds)
    # Full access default
    assert all(a["area_permissions"]["entries"] is True for a in auds)


@pytest.mark.asyncio
async def test_invite_with_restricted_areas(client: AsyncClient):
    await create_test_company(client, email="ra@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="ra@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _register_login(client, "tbonly@a.com")

    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "tbonly@a.com", "area_permissions": {"trial_balance": True}},
        headers=co,
    )
    assert resp.status_code == 200, resp.text
    aud = resp.json()["auditors"][0]
    assert aud["area_permissions"] == {
        "trial_balance": True, "entries": False, "requirements": False,
        "queries": False, "documents": False,
    }


@pytest.mark.asyncio
async def test_duplicate_live_and_pending_invites_rejected(client: AsyncClient):
    await create_test_company(client, email="dup@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="dup@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _register_login(client, "dupaud@a.com")

    r1 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "dupaud@a.com"}, headers=co)
    assert r1.status_code == 200
    r2 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "dupaud@a.com"}, headers=co)
    assert r2.status_code == 400

    # Unregistered email: second invite while pending is 409
    p1 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "ghost@firm.com"}, headers=co)
    assert p1.status_code == 200
    assert p1.json()["auditors"][-1]["status"] == "pending"
    p2 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "ghost@firm.com"}, headers=co)
    assert p2.status_code == 409


@pytest.mark.asyncio
async def test_remove_then_reinvite_resurrects_same_row(client: AsyncClient):
    await create_test_company(client, email="rr@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="rr@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _register_login(client, "comeback@a.com")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "comeback@a.com"}, headers=co)

    aud_id = (await client.get(f"/api/v1/auditease/engagements/{eng_id}", headers=co)).json()["auditors"][0]["auditor_id"]
    resp = await client.delete(f"/api/v1/auditease/engagements/{eng_id}/auditors/{aud_id}", headers=co)
    assert resp.status_code == 204

    # Re-invite succeeds despite the unique constraint (row resurrected)
    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "comeback@a.com", "area_permissions": {"queries": True}},
        headers=co,
    )
    assert resp.status_code == 200, resp.text
    auds = [a for a in resp.json()["auditors"] if a["status"] != "revoked"]
    assert len(auds) == 1
    assert auds[0]["auditor_id"] == aud_id
    assert auds[0]["area_permissions"] == {
        "trial_balance": False, "entries": False, "requirements": False,
        "queries": True, "documents": False,
    }


@pytest.mark.asyncio
async def test_employee_cannot_manage_auditors(client: AsyncClient):
    await create_test_company(client, email="emp@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="emp@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await _make_user(client, co, "staff@a.com", role="employee")
    emp = _headers(await get_company_token(client, email="staff@a.com", password="pass1234"))

    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "x@a.com"}, headers=emp)
    assert resp.status_code == 403
    # Reads stay open
    resp = await client.get(f"/api/v1/auditease/engagements/{eng_id}/auditors", headers=emp)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invite_on_closed_engagement_409(client: AsyncClient):
    await create_test_company(client, email="cl@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="cl@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=co)
    resp = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "x@a.com"}, headers=co)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_area_enforcement_blocks_disabled_areas(client: AsyncClient):
    import csv, io

    await create_test_company(client, email="ae@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="ae@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]

    # Import a minimal TB so trial-balance endpoints have data
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Ledger Name", "Closing"])
    w.writerow(["Sales", "100000"])
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/trial-balance/import",
        data={"column_map": '{"ledger_name": "Ledger Name", "closing_balance": "Closing"}'},
        files={"file": ("tb.csv", buf.getvalue(), "text/csv")},
        headers=co,
    )

    aud = await _register_login(client, "restricted@a.com")
    await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "restricted@a.com", "area_permissions": {}},
        headers=co,
    )
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud)

    # Every gated surface 403s with the clear message
    checks = [
        ("GET", f"/api/v1/auditor/engagements/{eng_id}/trial-balance", None),
        ("GET", f"/api/v1/auditor/engagements/{eng_id}/entries", None),
        ("POST", f"/api/v1/auditor/engagements/{eng_id}/entries",
         {"code": "ADJ1", "description": "d", "lines": []}),
        ("GET", f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", None),
        ("POST", f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
         {"description": "need docs"}),
        ("GET", f"/api/v1/auditor/engagements/{eng_id}/queries", None),
    ]
    for method, url, body in checks:
        if method == "GET":
            resp = await client.get(url, headers=aud)
        else:
            resp = await client.post(url, json=body, headers=aud)
        assert resp.status_code == 403, f"{method} {url} -> {resp.status_code}"
        assert "removed by the company" in resp.json()["detail"]

    # Accept + listing still work (no area gate)
    resp = await client.get("/api/v1/auditor/engagements", headers=aud)
    assert resp.status_code == 200 and len(resp.json()) == 1
    item = resp.json()[0]
    assert item["area_permissions"]["entries"] is False

    # Company widens access -> entries endpoint opens up
    aud_id = (await client.get(f"/api/v1/auditease/engagements/{eng_id}", headers=co)).json()["auditors"][0]["auditor_id"]
    resp = await client.patch(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/{aud_id}",
        json={"area_permissions": {"entries": True}},
        headers=co,
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/entries", headers=aud)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_workspace_actions_are_logged(client: AsyncClient):
    await create_test_company(client, email="lg@a.com", password="pass1234")
    co = _headers(await get_company_token(client, email="lg@a.com", password="pass1234"))
    eng_id = (await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co)).json()["id"]
    aud = await _register_login(client, "logger@a.com")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "logger@a.com"}, headers=co)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud)

    await client.post(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
                      json={"description": "Bank statements"}, headers=aud)
    req_id = (await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", headers=aud)).json()[0]["id"]
    await client.delete(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests/{req_id}", headers=aud)

    q = await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries",
                          data={"initial_message": "hello"}, headers=aud)
    assert q.status_code == 200, q.text
    query_id = q.json()["id"]
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries/{query_id}/messages",
                      data={"text": "any update?"}, headers=aud)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/queries/{query_id}/close", headers=aud)

    rows = await client.get("/api/v1/activity-log?limit=100", headers=co)
    got = {r["action"] for r in rows.json()}
    assert {"auditor.grant_accepted", "requirement.raised", "requirement.deleted",
            "query.opened", "query.replied", "query.closed"} <= got
