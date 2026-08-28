from unittest.mock import MagicMock, patch
import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token, create_test_auditor


@pytest.mark.asyncio
async def test_get_smtp_config_unconfigured(client: AsyncClient):
    await create_test_company(client, name="Co Unconfigured", email="admin@unconf.com")
    token = await get_company_token(client, email="admin@unconf.com")

    res = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is False


@pytest.mark.asyncio
async def test_save_and_get_smtp_config(client: AsyncClient):
    await create_test_company(client, name="Co Configured", email="admin@conf.com")
    token = await get_company_token(client, email="admin@conf.com")

    payload = {
        "host": "smtp.office365.com",
        "port": 587,
        "user": "audit@conf.com",
        "password": "Password123!",
        "use_tls": True,
        "use_ssl": False,
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    put_res = await client.put("/api/v1/company/smtp", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["configured"] is True
    assert data["host"] == "smtp.office365.com"
    assert data["port"] == 587
    assert data["user"] == "audit@conf.com"
    assert data["from_email"] == "audit@conf.com"
    assert data["has_password"] is True
    assert "password" not in data  # PASSWORD NEVER EXPOSED!

    get_res = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {token}"})
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["configured"] is True
    assert get_data["host"] == "smtp.office365.com"
    assert get_data["has_password"] is True
    assert "password" not in get_data


@pytest.mark.asyncio
@patch("app.routers.company_smtp.EmailService")
async def test_verify_smtp_config_success(mock_email_service_class, client: AsyncClient):
    mock_instance = MagicMock()
    mock_instance.verify_connection.return_value = {
        "host": "smtp.office365.com",
        "port": 587,
        "user": "audit@conf.com",
        "latency_ms": 145.2,
    }
    mock_email_service_class.return_value = mock_instance

    await create_test_company(client, name="Co Verify", email="admin@verify.com")
    token = await get_company_token(client, email="admin@verify.com")

    payload = {
        "host": "smtp.office365.com",
        "port": 587,
        "user": "audit@conf.com",
        "password": "Password123!",
        "use_tls": True,
        "use_ssl": False,
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    res = await client.post("/api/v1/company/smtp/verify", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["latency_ms"] == 145.2


@pytest.mark.asyncio
async def test_delete_smtp_config_resets_to_default(client: AsyncClient):
    await create_test_company(client, name="Co Delete", email="admin@del.com")
    token = await get_company_token(client, email="admin@del.com")

    # First configure
    payload = {
        "host": "smtp.office365.com",
        "port": 587,
        "user": "audit@del.com",
        "password": "Password123!",
        "use_tls": True,
        "use_ssl": False,
        "from_email": "audit@del.com",
        "from_name": "Del Compliance",
    }
    await client.put("/api/v1/company/smtp", json=payload, headers={"Authorization": f"Bearer {token}"})

    # Then delete
    del_res = await client.delete("/api/v1/company/smtp", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200
    assert del_res.json()["configured"] is False

    # Verify GET now returns configured=False
    get_res = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {token}"})
    assert get_res.json()["configured"] is False


@pytest.mark.asyncio
async def test_auditor_token_rejected_with_403_or_401(client: AsyncClient):
    await create_test_auditor(client, email="auditor@firm.com", password="password123")
    res = await client.post("/api/v1/auth/auditor/login", json={"email": "auditor@firm.com", "password": "password123"})
    auditor_token = res.json()["access_token"]

    get_res = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {auditor_token}"})
    assert get_res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_cross_tenant_isolation(client: AsyncClient):
    # Company A
    await create_test_company(client, name="Company A", email="admin@company-a.com")
    token_a = await get_company_token(client, email="admin@company-a.com")

    payload_a = {
        "host": "smtp.company-a.com",
        "port": 587,
        "user": "admin@company-a.com",
        "password": "PassA",
        "use_tls": True,
        "use_ssl": False,
        "from_email": "admin@company-a.com",
        "from_name": "Company A Admin",
    }
    await client.put("/api/v1/company/smtp", json=payload_a, headers={"Authorization": f"Bearer {token_a}"})

    # Company B
    await create_test_company(client, name="Company B", email="admin@company-b.com")
    token_b = await get_company_token(client, email="admin@company-b.com")

    # Company B's GET should NOT see Company A's host
    res_b = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.json()["configured"] is False
