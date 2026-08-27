import pytest
from httpx import AsyncClient
from app.models.company import UserRole
from tests.conftest import create_test_company, get_company_token


@pytest.mark.asyncio
async def test_user_role_enum_values():
    assert [e.value for e in UserRole] == ["admin", "employee"]
    assert not hasattr(UserRole, "manager")


@pytest.mark.asyncio
async def test_create_user_manager_role_rejected(client: AsyncClient):
    await create_test_company(client, email="admin@rbac.com", password="adminpass123")
    token = await get_company_token(client, email="admin@rbac.com", password="adminpass123")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "email": "testmgr@example.com",
        "password": "Password123!",
        "full_name": "Test Manager",
        "role": "manager",
    }
    response = await client.post("/api/v1/users", json=payload, headers=headers)
    assert response.status_code == 422
