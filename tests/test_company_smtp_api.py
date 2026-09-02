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
    await create_test_auditor(client, email="auditor@firm.com", password="Valid1!Pass")
    res = await client.post("/api/v1/auth/auditor/login", json={"email": "auditor@firm.com", "password": "Valid1!Pass"})
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

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "postgres",
        "redis",
        "169.254.169.254",
        "10.0.0.5",
        "[::1]",
        "100.64.0.1",
    ],
)
async def test_smtp_verify_refuses_internal_targets_and_masks_error(client: AsyncClient, host: str):
    email = f"admin-ssrf-{abs(hash(host)) % 100000}@ssrf.com"
    await create_test_company(client, name="Co Verify SSRF", email=email)
    token = await get_company_token(client, email=email)
    
    payload = {
        "host": host,
        "port": 587,
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.post("/api/v1/company/smtp/verify", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Could not connect to that mail server. Check the host, port and credentials."


@pytest.mark.asyncio
@pytest.mark.parametrize("port", [21, 22, 80, 443, 3306, 5432, 6379, 8080])
async def test_smtp_verify_refuses_non_smtp_ports_with_masked_error(client: AsyncClient, port: int):
    email = f"admin-port-{port}@ports.com"
    await create_test_company(client, name=f"Co Port {port}", email=email)
    token = await get_company_token(client, email=email)

    payload = {
        "host": "smtp.example.com",
        "port": port,
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.post("/api/v1/company/smtp/verify", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_smtp_verify_refuses_invalid_port_schema(client: AsyncClient):
    await create_test_company(client, name="Co Verify Schema", email="admin@schema.com")
    token = await get_company_token(client, email="admin@schema.com")
    
    payload = {
        "host": "smtp.example.com",
        "port": 99999,  # invalid port outside 1..65535
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.post("/api/v1/company/smtp/verify", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_smtp_verify_requires_password_for_new_host(client: AsyncClient):
    """If a saved config exists and user specifies a different host without password, reject with 400."""
    email = "admin-diff-host@test.com"
    await create_test_company(client, name="Co Diff Host", email=email)
    token = await get_company_token(client, email=email)

    # Save a configuration
    payload = {
        "host": "smtp.saved.com",
        "port": 587,
        "user": "saved@test.com",
        "password": "OldPassword123!",
        "from_email": "saved@test.com",
        "from_name": "Saved Sender",
    }
    await client.put("/api/v1/company/smtp", json=payload, headers={"Authorization": f"Bearer {token}"})

    # Try to verify a different host without providing a password
    verify_payload = {
        "host": "smtp.newtarget.com",
        "port": 587,
        "user": "saved@test.com",
    }
    r = await client.post("/api/v1/company/smtp/verify", json=verify_payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "Password is required when verifying a new SMTP host." in r.json()["detail"]


@pytest.mark.asyncio
@patch("app.routers.company_smtp.EmailService")
async def test_smtp_verify_adhoc_does_not_update_saved_last_tested_at(mock_email_service_class, client: AsyncClient):
    """Testing an arbitrary ad-hoc server must NOT update last_tested_at on the company's saved row."""
    mock_instance = MagicMock()
    mock_instance.verify_connection.return_value = {
        "status": "ok",
        "host": "smtp.adhoc.com",
        "port": 587,
        "user": "adhoc@test.com",
        "latency_ms": 50.0,
    }
    mock_email_service_class.return_value = mock_instance

    email = "admin-last-tested@test.com"
    await create_test_company(client, name="Co Last Tested", email=email)
    token = await get_company_token(client, email=email)

    # Save a configuration
    save_payload = {
        "host": "smtp.office365.com",
        "port": 587,
        "user": "actual@test.com",
        "password": "Password123!",
        "from_email": "actual@test.com",
        "from_name": "Actual Sender",
    }
    await client.put("/api/v1/company/smtp", json=save_payload, headers={"Authorization": f"Bearer {token}"})

    # Verify initial config has last_tested_at = None
    res = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {token}"})
    assert res.json()["last_tested_at"] is None

    # Test an ad-hoc different server
    adhoc_verify = {
        "host": "smtp.gmail.com",
        "port": 587,
        "user": "adhoc@test.com",
        "password": "AdhocPassword123!",
        "from_email": "adhoc@test.com",
        "from_name": "Adhoc Sender",
    }
    r = await client.post("/api/v1/company/smtp/verify", json=adhoc_verify, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # Verify saved config STILL has last_tested_at = None
    res = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {token}"})
    assert res.json()["last_tested_at"] is None

    # Now verify the saved config (by passing empty body or saved host)
    mock_instance.verify_connection.return_value = {
        "status": "ok",
        "host": "smtp.office365.com",
        "port": 587,
        "user": "actual@test.com",
        "latency_ms": 60.0,
    }
    r = await client.post("/api/v1/company/smtp/verify", json={}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # Verify saved config now HAS last_tested_at populated
    res = await client.get("/api/v1/company/smtp", headers={"Authorization": f"Bearer {token}"})
    assert res.json()["last_tested_at"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "postgres",
        "redis",
        "169.254.169.254",
        "10.0.0.5",
        "[::1]",
        "100.64.0.1",
    ],
)
async def test_save_smtp_config_refuses_internal_targets(client: AsyncClient, host: str):
    email = f"admin-save-ssrf-{abs(hash(host)) % 100000}@ssrf.com"
    await create_test_company(client, name="Co Save SSRF", email=email)
    token = await get_company_token(client, email=email)

    payload = {
        "host": host,
        "port": 587,
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.put("/api/v1/company/smtp", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Could not connect to that mail server. Check the host, port and credentials."


@pytest.mark.asyncio
@pytest.mark.parametrize("port", [21, 22, 80, 443, 3306, 5432, 6379, 8080, 0, 70000])
async def test_save_smtp_config_refuses_non_permitted_ports(client: AsyncClient, port: int):
    email = f"admin-save-port-{port}@ports.com"
    await create_test_company(client, name=f"Co Save Port {port}", email=email)
    token = await get_company_token(client, email=email)

    payload = {
        "host": "smtp.example.com",
        "port": port,
        "user": "audit@conf.com",
        "password": "Password123!",
        "from_email": "audit@conf.com",
        "from_name": "Conf Compliance",
    }
    r = await client.put("/api/v1/company/smtp", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


