import pytest
from httpx import AsyncClient
from tests.conftest import create_test_company, get_company_token


async def _create_user(
    client: AsyncClient,
    admin_headers: dict,
    email: str,
    password: str = "pass1234",
    role: str = "employee",
    modules: list[str] | None = None,
) -> str:
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": password,
            "full_name": "AuditEase Employee",
            "role": role,
            "accessible_modules": modules if modules is not None else ["auditease"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_non_admin_cannot_create_engagement(client: AsyncClient):
    await create_test_company(client, email="admin@ae-rbac.com", password="adminpass123")
    admin_token = await get_company_token(client, email="admin@ae-rbac.com", password="adminpass123")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    await _create_user(client, admin_headers, email="emp@ae-rbac.com", password="emppass123", role="employee", modules=["auditease"])
    emp_token = await get_company_token(client, email="emp@ae-rbac.com", password="emppass123")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Employee tries to create engagement -> 403
    res = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY 2024-25"}, headers=emp_headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_close_delete_or_invite_auditor(client: AsyncClient):
    await create_test_company(client, email="admin2@ae-rbac.com", password="adminpass123")
    admin_token = await get_company_token(client, email="admin2@ae-rbac.com", password="adminpass123")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin creates engagement
    create_res = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY 2024-25"}, headers=admin_headers)
    assert create_res.status_code == 201
    eng_id = create_res.json()["id"]

    # Create employee
    await _create_user(client, admin_headers, email="emp2@ae-rbac.com", password="emppass123", role="employee", modules=["auditease"])
    emp_token = await get_company_token(client, email="emp2@ae-rbac.com", password="emppass123")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Employee tries to invite auditor -> 403
    invite_res = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/invite",
        json={"email": "auditor@example.com"},
        headers=emp_headers,
    )
    assert invite_res.status_code == 403

    # Employee tries to close engagement -> 403
    close_res = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=emp_headers)
    assert close_res.status_code == 403

    # Employee tries to delete engagement -> 403
    del_res = await client.delete(f"/api/v1/auditease/engagements/{eng_id}", headers=emp_headers)
    assert del_res.status_code == 403

    # Admin can close and delete engagement
    admin_close_res = await client.patch(f"/api/v1/auditease/engagements/{eng_id}/close", headers=admin_headers)
    assert admin_close_res.status_code == 200

    admin_del_res = await client.delete(f"/api/v1/auditease/engagements/{eng_id}", headers=admin_headers)
    assert admin_del_res.status_code == 204
