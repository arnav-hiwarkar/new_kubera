"""Integration tests for Financial Years API."""
import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token


@pytest.mark.asyncio
async def test_financial_year_crud_and_lifecycle(client: AsyncClient):
    email = "admin_fy@testco.com"
    await create_test_company(client, name="FY Test Co", email=email)
    token = await get_company_token(client, email=email)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create Financial Year
    create_res = await client.post(
        "/api/v1/financial-years",
        json={
            "label": "2024-25",
            "start_date": "2024-04-01",
            "end_date": "2025-03-31",
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    fy = create_res.json()
    assert fy["label"] == "2024-25"
    assert fy["status"] == "open"
    fy_id = fy["id"]

    # 2. Duplicate label rejected
    dup_res = await client.post(
        "/api/v1/financial-years",
        json={
            "label": "2024-25",
            "start_date": "2024-04-01",
            "end_date": "2025-03-31",
        },
        headers=headers,
    )
    assert dup_res.status_code == 409

    # 3. Invalid date range rejected
    bad_date_res = await client.post(
        "/api/v1/financial-years",
        json={
            "label": "2025-26",
            "start_date": "2025-04-01",
            "end_date": "2024-03-31",
        },
        headers=headers,
    )
    assert bad_date_res.status_code == 422

    # 4. List Financial Years
    list_res = await client.get("/api/v1/financial-years", headers=headers)
    assert list_res.status_code == 200
    fys = list_res.json()
    assert len(fys) == 1
    assert fys[0]["id"] == fy_id

    # 5. Close Financial Year
    close_res = await client.post(f"/api/v1/financial-years/{fy_id}/close", headers=headers)
    assert close_res.status_code == 200
    assert close_res.json()["status"] == "closed"
    assert close_res.json()["closed_at"] is not None

    # 6. Reopen Financial Year
    reopen_res = await client.post(f"/api/v1/financial-years/{fy_id}/reopen", headers=headers)
    assert reopen_res.status_code == 200
    assert reopen_res.json()["status"] == "open"
    assert reopen_res.json()["closed_at"] is None
