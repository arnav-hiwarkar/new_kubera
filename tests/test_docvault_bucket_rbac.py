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
            "full_name": "Employee User",
            "role": role,
            "accessible_modules": modules if modules is not None else ["docvault"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_non_admin_cannot_create_or_delete_bucket(client: AsyncClient):
    # Setup company with admin
    await create_test_company(client, email="admin@docrbac.com", password="adminpass123")
    admin_token = await get_company_token(client, email="admin@docrbac.com", password="adminpass123")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin creates a bucket
    create_res = await client.post("/api/v1/docvault/buckets", json={"name": "Admin Bucket"}, headers=admin_headers)
    assert create_res.status_code == 201
    bucket_id = create_res.json()["id"]

    # Create employee user with docvault access
    await _create_user(client, admin_headers, email="emp@docrbac.com", password="emppass123", role="employee", modules=["docvault"])
    emp_token = await get_company_token(client, email="emp@docrbac.com", password="emppass123")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Non-admin attempts to create a bucket
    emp_create_res = await client.post("/api/v1/docvault/buckets", json={"name": "Emp Bucket"}, headers=emp_headers)
    assert emp_create_res.status_code == 403

    # Non-admin attempts to delete the bucket
    emp_del_res = await client.delete(f"/api/v1/docvault/buckets/{bucket_id}", headers=emp_headers)
    assert emp_del_res.status_code == 403

    # Admin deletes the bucket successfully
    admin_del_res = await client.delete(f"/api/v1/docvault/buckets/{bucket_id}", headers=admin_headers)
    assert admin_del_res.status_code == 204
