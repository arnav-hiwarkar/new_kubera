"""Tests for Phase 0: Auth endpoints (company + auditor), activity log, notifications."""
import pytest
from httpx import AsyncClient

from tests.conftest import (
    create_test_company,
    get_company_token,
    create_test_auditor,
    get_auditor_token,
    INTERNAL_API_KEY,
)


# === Company creation ===


@pytest.mark.asyncio
async def test_create_company(client: AsyncClient):
    data = await create_test_company(client)
    assert data["company"]["name"] == "TestCo"
    assert data["admin"]["email"] == "admin@testco.com"
    assert data["admin"]["role"] == "admin"


@pytest.mark.asyncio
async def test_create_company_bad_api_key(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/companies",
        json={"name": "Bad", "admin_email": "x@x.com"},
        headers={"X-Internal-Api-Key": "wrong-key"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_company_duplicate_email(client: AsyncClient):
    await create_test_company(client)
    resp = await client.post(
        "/api/v1/auth/companies",
        json={"name": "Co2", "admin_email": "admin@testco.com"},
        headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
    )
    assert resp.status_code == 409


# === Company login ===


@pytest.mark.asyncio
async def test_company_login(client: AsyncClient):
    await create_test_company(client)
    resp = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "admin@testco.com", "password": "testpass123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()
    assert "refresh_token" in resp.json()


@pytest.mark.asyncio
async def test_company_login_bad_password(client: AsyncClient):
    await create_test_company(client)
    resp = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "admin@testco.com", "password": "wrong"},
    )
    assert resp.status_code == 401


# === Company refresh ===


@pytest.mark.asyncio
async def test_company_refresh(client: AsyncClient):
    await create_test_company(client)
    login_resp = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "admin@testco.com", "password": "testpass123"},
    )
    refresh_token = login_resp.json()["refresh_token"]
    resp = await client.post(
        "/api/v1/auth/company/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# === Company /me ===


@pytest.mark.asyncio
async def test_company_me(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.get(
        "/api/v1/auth/company/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@testco.com"


# === Auditor registration ===


@pytest.mark.asyncio
async def test_auditor_register(client: AsyncClient):
    data = await create_test_auditor(client)
    assert data["email"] == "auditor@test.com"
    assert data["name"] == "Test Auditor"


@pytest.mark.asyncio
async def test_auditor_register_duplicate(client: AsyncClient):
    await create_test_auditor(client)
    resp = await client.post(
        "/api/v1/auth/auditor/register",
        json={"email": "auditor@test.com", "password": "pass1234", "name": "Dup"},
    )
    assert resp.status_code == 409


# === Auditor login ===


@pytest.mark.asyncio
async def test_auditor_login(client: AsyncClient):
    await create_test_auditor(client)
    resp = await client.post(
        "/api/v1/auth/auditor/login",
        json={"email": "auditor@test.com", "password": "testpass123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# === Auditor refresh ===


@pytest.mark.asyncio
async def test_auditor_refresh(client: AsyncClient):
    await create_test_auditor(client)
    login_resp = await client.post(
        "/api/v1/auth/auditor/login",
        json={"email": "auditor@test.com", "password": "testpass123"},
    )
    refresh_token = login_resp.json()["refresh_token"]
    resp = await client.post(
        "/api/v1/auth/auditor/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# === Auditor /me ===


@pytest.mark.asyncio
async def test_auditor_me(client: AsyncClient):
    await create_test_auditor(client)
    token = await get_auditor_token(client)
    resp = await client.get(
        "/api/v1/auth/auditor/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "auditor@test.com"


# === Cross-token-type rejection ===


@pytest.mark.asyncio
async def test_auditor_token_rejected_on_company_endpoint(client: AsyncClient):
    """Auditor token must not grant access to company endpoints."""
    await create_test_auditor(client)
    token = await get_auditor_token(client)
    resp = await client.get(
        "/api/v1/auth/company/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_company_token_rejected_on_auditor_endpoint(client: AsyncClient):
    """Company token must not grant access to auditor endpoints."""
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.get(
        "/api/v1/auth/auditor/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
