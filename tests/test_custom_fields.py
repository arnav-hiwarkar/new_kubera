import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token


async def _admin(client, email="cfadmin@a.com"):
    await create_test_company(client, email=email, password="pass1234")
    return {"Authorization": f"Bearer {await get_company_token(client, email=email, password='pass1234')}"}


async def _employee_headers(client, admin_headers, email):
    resp = await client.post(
        "/api/v1/users",
        json={"email": email, "password": "pass1234", "full_name": "Emp", "role": "employee"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    tok = await get_company_token(client, email=email, password="pass1234")
    return {"Authorization": f"Bearer {tok}"}


MOD = "asset_management"


@pytest.mark.asyncio
async def test_custom_field_lifecycle(client: AsyncClient):
    AH = await _admin(client)

    # Create
    resp = await client.post(
        f"/api/v1/custom-fields/{MOD}",
        json={"field_name": "Warranty", "field_key": "warranty", "field_type": "text", "display_order": 1},
        headers=AH,
    )
    assert resp.status_code == 201, resp.text
    fid = resp.json()["id"]
    assert resp.json()["is_active"] is True

    # Active list shows it
    active = await client.get(f"/api/v1/custom-fields/{MOD}", headers=AH)
    assert [f["id"] for f in active.json()] == [fid]

    # Deactivate -> hidden from default list, visible with include_inactive
    await client.patch(f"/api/v1/custom-fields/{MOD}/{fid}/deactivate", headers=AH)
    assert (await client.get(f"/api/v1/custom-fields/{MOD}", headers=AH)).json() == []
    incl = await client.get(f"/api/v1/custom-fields/{MOD}?include_inactive=true", headers=AH)
    assert [f["id"] for f in incl.json()] == [fid]
    assert incl.json()[0]["is_active"] is False

    # Reactivate
    await client.patch(f"/api/v1/custom-fields/{MOD}/{fid}/reactivate", headers=AH)
    assert (await client.get(f"/api/v1/custom-fields/{MOD}", headers=AH)).json()[0]["is_active"] is True


@pytest.mark.asyncio
async def test_custom_field_update_and_duplicate_key(client: AsyncClient):
    AH = await _admin(client, email="cf2@a.com")
    body = {"field_name": "Region", "field_key": "region", "field_type": "dropdown",
            "dropdown_options": ["North", "South"], "display_order": 0}
    fid = (await client.post(f"/api/v1/custom-fields/{MOD}", json=body, headers=AH)).json()["id"]

    # Update editable fields
    resp = await client.patch(
        f"/api/v1/custom-fields/{MOD}/{fid}",
        json={"field_name": "Sales Region", "is_required": True, "dropdown_options": ["N", "S", "E"], "display_order": 3},
        headers=AH,
    )
    assert resp.status_code == 200
    assert resp.json()["field_name"] == "Sales Region"
    assert resp.json()["is_required"] is True
    assert resp.json()["dropdown_options"] == ["N", "S", "E"]

    # Duplicate key -> 409
    dup = await client.post(f"/api/v1/custom-fields/{MOD}", json=body, headers=AH)
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_custom_field_module_isolation_and_auth(client: AsyncClient):
    AH = await _admin(client, email="cf3@a.com")
    await client.post(f"/api/v1/custom-fields/asset_management",
                      json={"field_name": "A", "field_key": "a", "field_type": "text"}, headers=AH)
    await client.post(f"/api/v1/custom-fields/sales_tracking",
                      json={"field_name": "B", "field_key": "b", "field_type": "text"}, headers=AH)

    assets = await client.get("/api/v1/custom-fields/asset_management", headers=AH)
    sales = await client.get("/api/v1/custom-fields/sales_tracking", headers=AH)
    assert {f["field_key"] for f in assets.json()} == {"a"}
    assert {f["field_key"] for f in sales.json()} == {"b"}

    # Non-admin cannot create
    EH = await _employee_headers(client, AH, "cfemp@a.com")
    resp = await client.post(f"/api/v1/custom-fields/{MOD}",
                             json={"field_name": "X", "field_key": "x", "field_type": "text"}, headers=EH)
    assert resp.status_code == 403
