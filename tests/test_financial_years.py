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
    reopen_res = await client.post(
        f"/api/v1/financial-years/{fy_id}/reopen",
        json={"reason": "fixing audit errors"},
        headers=headers,
    )
    assert reopen_res.status_code == 200
    assert reopen_res.json()["status"] == "open"
    assert reopen_res.json()["closed_at"] is None

    # 7. Verify close and reopen activity logs were created with full provenance
    log_res = await client.get(
        "/api/v1/activity-log",
        params={"entity_type": "financial_year", "entity_id": fy_id},
        headers=headers,
    )
    assert log_res.status_code == 200
    logs = log_res.json()
    reopen_log = next((l for l in logs if l["action"] == "financial_year.reopened"), None)
    assert reopen_log is not None
    assert reopen_log["metadata_"]["reason"] == "fixing audit errors"
    assert reopen_log["metadata_"]["was_closed_by"] is not None
    assert reopen_log["metadata_"]["was_closed_at"] is not None

    close_log = next((l for l in logs if l["action"] == "financial_year.closed"), None)
    assert close_log is not None
    assert close_log["metadata_"]["label"] == "2024-25"


@pytest.mark.asyncio
async def test_employee_cannot_close_or_reopen_financial_year(client: AsyncClient):
    email = "admin_fy_employee@testco.com"
    emp_email = "employee_fy@testco.com"
    await create_test_company(client, name="FY Employee Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Create employee user with assets module
    create_emp_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": emp_email,
            "password": "Valid1!Pass",
            "full_name": "Employee",
            "role": "employee",
            "accessible_modules": ["assets"],
        },
    )
    assert create_emp_res.status_code == 201

    emp_token = await get_company_token(client, email=emp_email, password="Valid1!Pass")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Admin creates financial year
    create_res = await client.post(
        "/api/v1/financial-years",
        json={
            "label": "2024-25",
            "start_date": "2024-04-01",
            "end_date": "2025-03-31",
        },
        headers=admin_headers,
    )
    assert create_res.status_code == 201
    fy_id = create_res.json()["id"]

    # Employee can list financial years because they have "assets" module
    emp_list = await client.get("/api/v1/financial-years", headers=emp_headers)
    assert emp_list.status_code == 200

    # Employee cannot close FY -> 403 Forbidden
    close_res = await client.post(
        f"/api/v1/financial-years/{fy_id}/close",
        headers=emp_headers,
    )
    assert close_res.status_code == 403

    # Admin closes FY
    admin_close = await client.post(f"/api/v1/financial-years/{fy_id}/close", headers=admin_headers)
    assert admin_close.status_code == 200

    # Employee cannot reopen FY -> 403 Forbidden
    reopen_res = await client.post(
        f"/api/v1/financial-years/{fy_id}/reopen",
        json={"reason": "employee trying to reopen period"},
        headers=emp_headers,
    )
    assert reopen_res.status_code == 403


@pytest.mark.asyncio
async def test_employee_without_assets_module_cannot_access_financial_years(client: AsyncClient):
    email = "admin_fy_noassets@testco.com"
    emp_email = "employee_fy_noassets@testco.com"
    await create_test_company(client, name="FY No Assets Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_emp_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": emp_email,
            "password": "Valid1!Pass",
            "full_name": "No Assets Employee",
            "role": "employee",
            "accessible_modules": ["docvault"],
        },
    )
    assert create_emp_res.status_code == 201

    emp_token = await get_company_token(client, email=emp_email, password="Valid1!Pass")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Employee without assets module cannot list FYs -> 403
    list_res = await client.get("/api/v1/financial-years", headers=emp_headers)
    assert list_res.status_code == 403

    # Employee without assets module cannot create FY -> 403
    create_res = await client.post(
        "/api/v1/financial-years",
        json={
            "label": "2024-25",
            "start_date": "2024-04-01",
            "end_date": "2025-03-31",
        },
        headers=emp_headers,
    )
    assert create_res.status_code == 403


@pytest.mark.asyncio
async def test_financial_year_edge_cases_and_anti_tests(client: AsyncClient):
    email = "admin_fy_edge@testco.com"
    await create_test_company(client, name="FY Edge Co", email=email)
    token = await get_company_token(client, email=email)
    headers = {"Authorization": f"Bearer {token}"}

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
    fy_id = create_res.json()["id"]

    # 1. Cannot reopen an already OPEN financial year -> 409
    reopen_open = await client.post(
        f"/api/v1/financial-years/{fy_id}/reopen",
        json={"reason": "already open period"},
        headers=headers,
    )
    assert reopen_open.status_code == 409
    assert "not closed" in reopen_open.json()["detail"].lower()

    # 2. Close FY
    close_ok = await client.post(f"/api/v1/financial-years/{fy_id}/close", headers=headers)
    assert close_ok.status_code == 200

    # 3. Cannot close an already CLOSED financial year -> 409
    close_closed = await client.post(f"/api/v1/financial-years/{fy_id}/close", headers=headers)
    assert close_closed.status_code == 409
    assert "already closed" in close_closed.json()["detail"].lower()

    # 4. Anti-test: Reopen without reason body -> 422
    reopen_no_body = await client.post(
        f"/api/v1/financial-years/{fy_id}/reopen",
        headers=headers,
    )
    assert reopen_no_body.status_code == 422

    # 5. Anti-test: Reopen with short reason (< 10 chars) -> 422
    reopen_short = await client.post(
        f"/api/v1/financial-years/{fy_id}/reopen",
        json={"reason": "short"},
        headers=headers,
    )
    assert reopen_short.status_code == 422

    # 6. Anti-test: Reopen with whitespace-only reason (e.g. 15 spaces) -> 422
    reopen_spaces = await client.post(
        f"/api/v1/financial-years/{fy_id}/reopen",
        json={"reason": "               "},
        headers=headers,
    )
    assert reopen_spaces.status_code == 422

    # 7. Valid reopen succeeds
    reopen_ok = await client.post(
        f"/api/v1/financial-years/{fy_id}/reopen",
        json={"reason": "legitimate reopening reason"},
        headers=headers,
    )
    assert reopen_ok.status_code == 200
    assert reopen_ok.json()["status"] == "open"
