import json

import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token


async def _admin(client, email="asadmin@a.com"):
    await create_test_company(client, email=email, password="pass")
    return {"Authorization": f"Bearer {await get_company_token(client, email=email, password='pass')}"}


async def _make_user(client, admin_headers, email, role="employee", manager_id=None):
    body = {"email": email, "password": "pass", "full_name": email.split("@")[0], "role": role}
    if manager_id:
        body["manager_id"] = manager_id
    resp = await client.post("/api/v1/users", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _headers(client, email):
    return {"Authorization": f"Bearer {await get_company_token(client, email=email, password='pass')}"}


@pytest.mark.asyncio
async def test_asset_crud(client: AsyncClient):
    AH = await _admin(client)
    resp = await client.post(
        "/api/v1/assets",
        json={"asset_name": "Laptop", "category": "hardware", "purchase_cost": 1200},
        headers=AH,
    )
    assert resp.status_code == 201, resp.text
    aid = resp.json()["id"]
    assert resp.json()["status"] == "active"

    assert (await client.get(f"/api/v1/assets/{aid}", headers=AH)).status_code == 200
    assert len((await client.get("/api/v1/assets", headers=AH)).json()) == 1

    resp = await client.patch(f"/api/v1/assets/{aid}", json={"status": "maintenance"}, headers=AH)
    assert resp.json()["status"] == "maintenance"


@pytest.mark.asyncio
async def test_asset_custom_field_validation(client: AsyncClient):
    AH = await _admin(client, email="ascf@a.com")
    # A required dropdown custom field
    await client.post(
        "/api/v1/custom-fields/asset_management",
        json={"field_name": "Region", "field_key": "region", "field_type": "dropdown",
              "dropdown_options": ["North", "South"], "is_required": True},
        headers=AH,
    )

    # Missing required custom field -> 400
    resp = await client.post(
        "/api/v1/assets",
        json={"asset_name": "A1", "category": "hardware"},
        headers=AH,
    )
    assert resp.status_code == 400
    assert "custom_field_errors" in resp.json()["detail"]

    # Invalid dropdown value -> 400
    resp = await client.post(
        "/api/v1/assets",
        json={"asset_name": "A2", "category": "hardware", "custom_fields": {"region": "West"}},
        headers=AH,
    )
    assert resp.status_code == 400

    # Valid value -> 201
    resp = await client.post(
        "/api/v1/assets",
        json={"asset_name": "A3", "category": "hardware", "custom_fields": {"region": "North"}},
        headers=AH,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["custom_fields"]["region"] == "North"


ASSET_CSV = (
    b"Name,Serial,Cat,Cost,PurchDate,Warranty\n"
    b"Laptop,SN1,hardware,1000,2024-03-15,1yr\n"
    b"Desk,SN2,furniture,200,not-a-date,2yr\n"
)


@pytest.mark.asyncio
async def test_asset_import_inspect_and_import(client: AsyncClient):
    AH = await _admin(client, email="asimp@a.com")
    # optional custom field for import
    await client.post(
        "/api/v1/custom-fields/asset_management",
        json={"field_name": "Warranty", "field_key": "warranty", "field_type": "text"},
        headers=AH,
    )

    # Inspect returns headers
    inspect = await client.post(
        "/api/v1/assets/import/inspect",
        files={"file": ("assets.csv", ASSET_CSV, "text/csv")},
        headers=AH,
    )
    assert inspect.status_code == 200, inspect.text
    headers = inspect.json()["sheets"][0]["headers"]
    assert headers == ["Name", "Serial", "Cat", "Cost", "PurchDate", "Warranty"]

    mappings = [
        {"source_column": "Name", "target_field": "asset_name"},
        {"source_column": "Serial", "target_field": "serial_number"},
        {"source_column": "Cat", "target_field": "category"},
        {"source_column": "Cost", "target_field": "purchase_cost"},
        {"source_column": "PurchDate", "target_field": "purchase_date"},
        {"source_column": "Warranty", "target_field": "warranty"},
    ]
    imp = await client.post(
        "/api/v1/assets/import",
        files={"file": ("assets.csv", ASSET_CSV, "text/csv")},
        data={"mappings": json.dumps(mappings)},
        headers=AH,
    )
    assert imp.status_code == 200, imp.text
    body = imp.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1
    assert body["errors"][0]["row"] == 2  # bad date row

    # Imported asset carries parsed date + custom field
    assets = (await client.get("/api/v1/assets", headers=AH)).json()
    assert len(assets) == 1
    row = assets[0]
    assert row["purchase_date"] == "2024-03-15"
    assert row["custom_fields"]["warranty"] == "1yr"


@pytest.mark.asyncio
async def test_asset_export(client: AsyncClient):
    AH = await _admin(client, email="asexp@a.com")
    await client.post("/api/v1/assets", json={"asset_name": "L", "category": "hardware"}, headers=AH)
    resp = await client.get("/api/v1/assets/export/excel", headers=AH)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["content-type"]
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_asset_admin_only_and_scoping(client: AsyncClient):
    AH = await _admin(client, email="asauth@a.com")
    emp_a = await _make_user(client, AH, "empa@a.com")
    await _make_user(client, AH, "empb@a.com")
    EH_a = await _headers(client, "empa@a.com")
    EH_b = await _headers(client, "empb@a.com")

    # Non-admin cannot create
    assert (await client.post("/api/v1/assets", json={"asset_name": "X", "category": "hardware"}, headers=EH_a)).status_code == 403

    # Admin creates one asset assigned to emp A, one unassigned
    await client.post("/api/v1/assets", json={"asset_name": "A-asset", "category": "hardware", "custodian_id": emp_a["id"]}, headers=AH)
    await client.post("/api/v1/assets", json={"asset_name": "Shared", "category": "hardware"}, headers=AH)

    # Emp B sees only the unassigned asset, not emp A's
    names_b = {a["asset_name"] for a in (await client.get("/api/v1/assets", headers=EH_b)).json()}
    assert "Shared" in names_b
    assert "A-asset" not in names_b

    # Emp A sees their own + the unassigned
    names_a = {a["asset_name"] for a in (await client.get("/api/v1/assets", headers=EH_a)).json()}
    assert {"A-asset", "Shared"}.issubset(names_a)
