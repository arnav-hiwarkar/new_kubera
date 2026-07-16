import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token, INTERNAL_API_KEY


async def _admin(client, email="kadmin@a.com"):
    await create_test_company(client, email=email, password="pass1234")
    return {"Authorization": f"Bearer {await get_company_token(client, email=email, password='pass1234')}"}


async def _make_user(client, admin_headers, email, role, manager_id=None):
    body = {"email": email, "password": "pass1234", "full_name": email.split("@")[0], "role": role}
    if manager_id:
        body["manager_id"] = manager_id
    resp = await client.post("/api/v1/users", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _headers(client, email):
    tok = await get_company_token(client, email=email, password="pass1234")
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_kra_full_lifecycle(client: AsyncClient):
    AH = await _admin(client)
    mgr = await _make_user(client, AH, "m1@a.com", "manager")
    await _make_user(client, AH, "e1@a.com", "employee", manager_id=mgr["id"])
    MH = await _headers(client, "m1@a.com")
    EH = await _headers(client, "e1@a.com")

    # Employee creates own KRA — starts as draft, manager auto-attached from hierarchy.
    resp = await client.post(
        "/api/v1/kra",
        json={"title": "Ship v1", "description": "Launch", "weightage": 40, "cycle": "FY25-Q1"},
        headers=EH,
    )
    assert resp.status_code == 201, resp.text
    kra = resp.json()
    assert kra["status"] == "draft"
    assert kra["manager_id"] == mgr["id"]
    kid = kra["id"]

    # Submit for approval
    assert (await client.patch(f"/api/v1/kra/{kid}", json={"status": "pending_approval"}, headers=EH)).json()["status"] == "pending_approval"

    # Manager approves -> in_progress (single step)
    assert (await client.patch(f"/api/v1/kra/{kid}", json={"status": "in_progress"}, headers=MH)).json()["status"] == "in_progress"

    # Employee submits self-review
    r = await client.patch(
        f"/api/v1/kra/{kid}",
        json={"status": "review_submitted", "employee_self_rating": 4, "employee_comment": "solid"},
        headers=EH,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "review_submitted"
    assert r.json()["employee_self_rating"] == 4

    # Manager completes with a rating
    r = await client.patch(
        f"/api/v1/kra/{kid}",
        json={"status": "completed", "manager_rating": 5, "manager_comment": "great"},
        headers=MH,
    )
    assert r.json()["status"] == "completed"
    assert r.json()["manager_rating"] == 5


@pytest.mark.asyncio
async def test_kra_visibility_scope(client: AsyncClient):
    AH = await _admin(client, email="kadmin2@a.com")
    mgr = await _make_user(client, AH, "m2@a.com", "manager")
    await _make_user(client, AH, "e2a@a.com", "employee", manager_id=mgr["id"])
    await _make_user(client, AH, "e2b@a.com", "employee")  # reports to no one
    EH_a = await _headers(client, "e2a@a.com")
    EH_b = await _headers(client, "e2b@a.com")
    MH = await _headers(client, "m2@a.com")

    ka = (await client.post("/api/v1/kra", json={"title": "A", "description": "d", "cycle": "C"}, headers=EH_a)).json()
    kb = (await client.post("/api/v1/kra", json={"title": "B", "description": "d", "cycle": "C"}, headers=EH_b)).json()

    # Employee A sees only their own
    ids_a = {k["id"] for k in (await client.get("/api/v1/kra", headers=EH_a)).json()}
    assert ka["id"] in ids_a and kb["id"] not in ids_a

    # Manager sees their report's KRA but not the unrelated employee's
    ids_m = {k["id"] for k in (await client.get("/api/v1/kra", headers=MH)).json()}
    assert ka["id"] in ids_m and kb["id"] not in ids_m

    # Admin sees everything
    ids_admin = {k["id"] for k in (await client.get("/api/v1/kra", headers=AH)).json()}
    assert {ka["id"], kb["id"]}.issubset(ids_admin)


@pytest.mark.asyncio
async def test_kra_permissions_and_rejection(client: AsyncClient):
    AH = await _admin(client, email="kadmin3@a.com")
    mgr = await _make_user(client, AH, "m3@a.com", "manager")
    await _make_user(client, AH, "e3@a.com", "employee", manager_id=mgr["id"])
    MH = await _headers(client, "m3@a.com")
    EH = await _headers(client, "e3@a.com")

    kid = (await client.post("/api/v1/kra", json={"title": "X", "description": "d", "cycle": "C"}, headers=EH)).json()["id"]

    # Employee cannot set a manager rating
    assert (await client.patch(f"/api/v1/kra/{kid}", json={"manager_rating": 3}, headers=EH)).status_code == 403
    # Employee cannot approve their own plan
    await client.patch(f"/api/v1/kra/{kid}", json={"status": "pending_approval"}, headers=EH)
    assert (await client.patch(f"/api/v1/kra/{kid}", json={"status": "approved"}, headers=EH)).status_code == 403

    # Manager rejects with a reason
    r = await client.patch(
        f"/api/v1/kra/{kid}",
        json={"status": "rejected", "rejection_reason": "scope unclear"},
        headers=MH,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["rejection_reason"] == "scope unclear"
