import json

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token


async def _admin(client, email="sadmin@a.com"):
    await create_test_company(client, email=email, password="pass1234")
    return {"Authorization": f"Bearer {await get_company_token(client, email=email, password='pass1234')}"}


async def _make_user(client, admin_headers, email, role="employee", manager_id=None):
    body = {"email": email, "password": "pass1234", "full_name": email.split("@")[0], "role": role}
    if manager_id:
        body["manager_id"] = manager_id
    resp = await client.post("/api/v1/users", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _headers(client, email):
    return {"Authorization": f"Bearer {await get_company_token(client, email=email, password='pass1234')}"}


@pytest.mark.asyncio
async def test_sales_crud_by_employee(client: AsyncClient):
    AH = await _admin(client)
    await _make_user(client, AH, "srep@a.com")
    EH = await _headers(client, "srep@a.com")

    # A non-admin can create their own record (Sales is not admin-only).
    resp = await client.post(
        "/api/v1/sales",
        json={"client_name": "Acme", "product_service": "Widgets", "amount": 5000, "status": "lead"},
        headers=EH,
    )
    assert resp.status_code == 201, resp.text
    sid = resp.json()["id"]
    assert resp.json()["status"] == "lead"

    assert (await client.get(f"/api/v1/sales/{sid}", headers=EH)).status_code == 200
    resp = await client.patch(f"/api/v1/sales/{sid}", json={"status": "won"}, headers=EH)
    assert resp.json()["status"] == "won"


@pytest.mark.asyncio
async def test_sales_custom_field_validation(client: AsyncClient):
    AH = await _admin(client, email="scf@a.com")
    await client.post(
        "/api/v1/custom-fields/sales_tracking",
        json={"field_name": "Tier", "field_key": "tier", "field_type": "dropdown",
              "dropdown_options": ["Gold", "Silver"], "is_required": True},
        headers=AH,
    )
    base = {"client_name": "A", "product_service": "P", "amount": 1}
    # Missing required custom field -> 400 (enforced even when custom_fields omitted)
    r = await client.post("/api/v1/sales", json=base, headers=AH)
    assert r.status_code == 400
    assert "custom_field_errors" in r.json()["detail"]
    # Valid -> 201
    r = await client.post("/api/v1/sales", json={**base, "custom_fields": {"tier": "Gold"}}, headers=AH)
    assert r.status_code == 201, r.text
    assert r.json()["custom_fields"]["tier"] == "Gold"


@pytest.mark.asyncio
async def test_sales_aggregate(client: AsyncClient):
    AH = await _admin(client, email="sagg@a.com")
    for amt, st in [(100, "won"), (200, "won"), (50, "lead")]:
        await client.post("/api/v1/sales", json={"client_name": "C", "product_service": "P", "amount": amt, "status": st}, headers=AH)
    agg = {row["status"]: row for row in (await client.get("/api/v1/sales/aggregate", headers=AH)).json()}
    assert agg["won"]["count"] == 2 and agg["won"]["total_amount"] == 300.0
    assert agg["lead"]["count"] == 1 and agg["lead"]["total_amount"] == 50.0


SALES_CSV = (
    b"Client,Product,Amount,Stage,Tier\n"
    b"Acme,Widgets,5000,won,Gold\n"
    b"Beta,Gadgets,notnum,lead,Silver\n"
)


@pytest.mark.asyncio
async def test_sales_import_inspect_and_import(client: AsyncClient):
    AH = await _admin(client, email="simp@a.com")
    await client.post(
        "/api/v1/custom-fields/sales_tracking",
        json={"field_name": "Tier", "field_key": "tier", "field_type": "text"},
        headers=AH,
    )
    inspect = await client.post(
        "/api/v1/sales/import/inspect",
        files={"file": ("sales.csv", SALES_CSV, "text/csv")},
        headers=AH,
    )
    assert inspect.status_code == 200, inspect.text
    assert inspect.json()["sheets"][0]["headers"] == ["Client", "Product", "Amount", "Stage", "Tier"]

    mappings = [
        {"source_column": "Client", "target_field": "client_name"},
        {"source_column": "Product", "target_field": "product_service"},
        {"source_column": "Amount", "target_field": "amount"},
        {"source_column": "Stage", "target_field": "status"},
        {"source_column": "Tier", "target_field": "tier"},
    ]
    imp = await client.post(
        "/api/v1/sales/import",
        files={"file": ("sales.csv", SALES_CSV, "text/csv")},
        data={"mappings": json.dumps(mappings)},
        headers=AH,
    )
    assert imp.status_code == 200, imp.text
    body = imp.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1  # bad amount row
    assert body["errors"][0]["row"] == 2

    rows = (await client.get("/api/v1/sales", headers=AH)).json()
    assert len(rows) == 1
    assert rows[0]["client_name"] == "Acme"
    assert rows[0]["custom_fields"]["tier"] == "Gold"


@pytest.mark.asyncio
async def test_sales_scoping_and_attribution(client: AsyncClient):
    AH = await _admin(client, email="ssc@a.com")
    mgr = await _make_user(client, AH, "smgr@a.com", role="manager")
    emp = await _make_user(client, AH, "semp@a.com", manager_id=mgr["id"])
    other = await _make_user(client, AH, "soth@a.com")
    MH = await _headers(client, "smgr@a.com")
    EH = await _headers(client, "semp@a.com")

    # Employee creates own sale
    s = (await client.post("/api/v1/sales", json={"client_name": "E", "product_service": "P", "amount": 10}, headers=EH)).json()
    assert s["user_id"] == emp["id"]

    # Manager sees the report's sale; the unrelated employee does not
    mgr_ids = {r["id"] for r in (await client.get("/api/v1/sales", headers=MH)).json()}
    assert s["id"] in mgr_ids
    OH = await _headers(client, "soth@a.com")
    other_ids = {r["id"] for r in (await client.get("/api/v1/sales", headers=OH)).json()}
    assert s["id"] not in other_ids

    # Manager can attribute a sale to their report; employee cannot attribute to someone else
    r = await client.post("/api/v1/sales", json={"client_name": "X", "product_service": "P", "amount": 5, "user_id": emp["id"]}, headers=MH)
    assert r.status_code == 201
    r = await client.post("/api/v1/sales", json={"client_name": "Y", "product_service": "P", "amount": 5, "user_id": other["id"]}, headers=EH)
    assert r.status_code == 403
