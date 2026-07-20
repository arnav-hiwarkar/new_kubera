"""Tests for company distribution/onboarding: operator init, admin activation
via one-shot key, key reissue, backend list/delete, company profile + logo,
and login rate limiting."""
import base64

import pytest
from httpx import AsyncClient

from tests.conftest import (
    init_company,
    activate_company,
    create_test_company,
    get_company_token,
    INTERNAL_API_KEY,
)

BAD_KEY = {"X-Internal-Api-Key": "wrong-key"}
GOOD_KEY = {"X-Internal-Api-Key": INTERNAL_API_KEY}

# 1x1 transparent PNG
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


async def _make_employee(client, admin_headers, email="emp@testco.com"):
    resp = await client.post(
        "/api/v1/users",
        json={"email": email, "password": "emppass123", "full_name": "Emp", "role": "employee"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ============================ Initialization ============================


@pytest.mark.asyncio
async def test_init_returns_key_and_pending_admin(client: AsyncClient):
    data = await init_company(client, name="Acme", email="a@acme.com")
    assert data["company"]["name"] == "Acme"
    assert data["admin"]["email"] == "a@acme.com"
    assert data["admin"]["role"] == "admin"
    assert data["admin"]["is_active"] is False
    assert data["activation_key"]
    assert data["activation_expires_at"]


@pytest.mark.asyncio
async def test_login_blocked_before_activation(client: AsyncClient):
    await init_company(client, email="a@acme.com")
    resp = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "a@acme.com", "password": "anything123"},
    )
    assert resp.status_code == 401


# ============================ Activation ============================


@pytest.mark.asyncio
async def test_activate_wrong_key_generic_400(client: AsyncClient):
    await init_company(client, email="a@acme.com")
    resp = await client.post(
        "/api/v1/auth/company/activate",
        json={"email": "a@acme.com", "activation_key": "nope", "password": "realpass123", "full_name": "A"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired activation details"


@pytest.mark.asyncio
async def test_activate_unknown_email_generic_400(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/company/activate",
        json={"email": "ghost@nowhere.com", "activation_key": "nope", "password": "realpass123", "full_name": "A"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired activation details"


@pytest.mark.asyncio
async def test_activate_short_password_422(client: AsyncClient):
    data = await init_company(client, email="a@acme.com")
    resp = await client.post(
        "/api/v1/auth/company/activate",
        json={"email": "a@acme.com", "activation_key": data["activation_key"], "password": "short", "full_name": "A"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_activate_success_then_login(client: AsyncClient):
    data = await init_company(client, email="a@acme.com")
    await activate_company(client, "a@acme.com", data["activation_key"], password="realpass123", full_name="Ada")
    resp = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "a@acme.com", "password": "realpass123"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Ada"
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_activate_key_is_one_shot(client: AsyncClient):
    data = await init_company(client, email="a@acme.com")
    await activate_company(client, "a@acme.com", data["activation_key"])
    # Re-using the same key must now fail.
    resp = await client.post(
        "/api/v1/auth/company/activate",
        json={"email": "a@acme.com", "activation_key": data["activation_key"], "password": "realpass123", "full_name": "A"},
    )
    assert resp.status_code == 400


# ============================ Reissue ============================


@pytest.mark.asyncio
async def test_reissue_invalidates_old_key_and_new_key_works(client: AsyncClient):
    data = await init_company(client, name="Acme", email="a@acme.com")
    cid = data["company"]["id"]
    old_key = data["activation_key"]

    reissue = await client.post(f"/api/v1/auth/companies/{cid}/reissue-key", headers=GOOD_KEY)
    assert reissue.status_code == 200
    new_key = reissue.json()["activation_key"]
    assert new_key != old_key

    # Old key no longer valid.
    bad = await client.post(
        "/api/v1/auth/company/activate",
        json={"email": "a@acme.com", "activation_key": old_key, "password": "realpass123", "full_name": "A"},
    )
    assert bad.status_code == 400

    # New key activates.
    await activate_company(client, "a@acme.com", new_key)


@pytest.mark.asyncio
async def test_reissue_after_activation_409(client: AsyncClient):
    data = await create_test_company(client, name="Acme", email="a@acme.com")
    cid = data["company"]["id"]
    resp = await client.post(f"/api/v1/auth/companies/{cid}/reissue-key", headers=GOOD_KEY)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_reissue_bad_key_403(client: AsyncClient):
    data = await init_company(client)
    resp = await client.post(f"/api/v1/auth/companies/{data['company']['id']}/reissue-key", headers=BAD_KEY)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reissue_unknown_company_404(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/companies/00000000-0000-0000-0000-000000000000/reissue-key",
        headers=GOOD_KEY,
    )
    assert resp.status_code == 404


# ============================ List (backend only) ============================


@pytest.mark.asyncio
async def test_list_companies_shows_status(client: AsyncClient):
    await create_test_company(client, name="Active Co", email="active@co.com")
    await init_company(client, name="Pending Co", email="pending@co.com")

    resp = await client.get("/api/v1/auth/companies", headers=GOOD_KEY)
    assert resp.status_code == 200
    by_name = {c["name"]: c for c in resp.json()}

    assert by_name["Active Co"]["admin_active"] is True
    assert by_name["Active Co"]["activation_pending"] is False

    assert by_name["Pending Co"]["admin_active"] is False
    assert by_name["Pending Co"]["activation_pending"] is True
    assert by_name["Pending Co"]["admin_email"] == "pending@co.com"


@pytest.mark.asyncio
async def test_list_bad_key_403(client: AsyncClient):
    resp = await client.get("/api/v1/auth/companies", headers=BAD_KEY)
    assert resp.status_code == 403


# ============================ Delete (backend only) ============================


@pytest.mark.asyncio
async def test_delete_archives_and_blocks_login(client: AsyncClient):
    data = await create_test_company(client, name="Doomed Co", email="doom@co.com")
    cid = data["company"]["id"]
    token = await get_company_token(client, email="doom@co.com")
    # Seed a tenant child row (employee) so the delete has attached work to handle.
    await _make_employee(client, {"Authorization": f"Bearer {token}"}, email="e@doom.com")

    resp = await client.request(
        "DELETE", f"/api/v1/auth/companies/{cid}",
        headers=GOOD_KEY, json={"confirm_name": "Doomed Co"},
    )
    assert resp.status_code == 204

    # Company is retained but marked archived (encrypted data is not destroyed).
    listed = await client.get("/api/v1/auth/companies", headers=GOOD_KEY)
    entry = next((c for c in listed.json() if c["id"] == cid), None)
    assert entry is not None and entry["archived"] is True

    # Admin can no longer log in (all users deactivated + company archived).
    login = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "doom@co.com", "password": "testpass123"},
    )
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_delete_wrong_confirm_name_400(client: AsyncClient):
    data = await create_test_company(client, name="Keep Co", email="keep@co.com")
    resp = await client.request(
        "DELETE", f"/api/v1/auth/companies/{data['company']['id']}",
        headers=GOOD_KEY, json={"confirm_name": "Wrong Name"},
    )
    assert resp.status_code == 400
    # Still there.
    listed = await client.get("/api/v1/auth/companies", headers=GOOD_KEY)
    assert any(c["id"] == data["company"]["id"] for c in listed.json())


@pytest.mark.asyncio
async def test_delete_bad_key_403(client: AsyncClient):
    data = await create_test_company(client, name="Keep Co", email="keep@co.com")
    resp = await client.request(
        "DELETE", f"/api/v1/auth/companies/{data['company']['id']}",
        headers=BAD_KEY, json={"confirm_name": "Keep Co"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_unknown_404(client: AsyncClient):
    resp = await client.request(
        "DELETE", "/api/v1/auth/companies/00000000-0000-0000-0000-000000000000",
        headers=GOOD_KEY, json={"confirm_name": "x"},
    )
    assert resp.status_code == 404


# ============================ Profile ============================


@pytest.mark.asyncio
async def test_get_profile_incomplete_initially(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.get("/api/v1/company/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["profile_completed"] is False
    assert resp.json()["has_logo"] is False


@pytest.mark.asyncio
async def test_update_profile_bad_pan_422(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.put(
        "/api/v1/company/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"pan": "NOTAPAN"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_profile_bad_gstin_and_cin_422(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    h = {"Authorization": f"Bearer {token}"}
    assert (await client.put("/api/v1/company/profile", headers=h, json={"gstin": "BAD"})).status_code == 422
    assert (await client.put("/api/v1/company/profile", headers=h, json={"cin": "BAD"})).status_code == 422


@pytest.mark.asyncio
async def test_update_profile_partial_keeps_incomplete(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.put(
        "/api/v1/company/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"legal_name": "Test Pvt Ltd", "pan": "abcde1234f"},
    )
    assert resp.status_code == 200
    # Normalization to uppercase.
    assert resp.json()["pan"] == "ABCDE1234F"
    assert resp.json()["profile_completed"] is False


@pytest.mark.asyncio
async def test_update_profile_all_required_completes(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.put(
        "/api/v1/company/profile",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "legal_name": "Test Pvt Ltd",
            "cin": "U12345MH2020PTC123456",
            "pan": "ABCDE1234F",
            "gstin": "27ABCDE1234F1Z5",
            "address_line1": "1 MG Road",
            "city": "Mumbai",
            "state": "MH",
            "pincode": "400001",
            "contact_email": "hello@test.com",
            "contact_phone": "9876543210",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["profile_completed"] is True


@pytest.mark.asyncio
async def test_employee_can_view_but_not_edit_profile(client: AsyncClient):
    data = await create_test_company(client)
    admin_token = await get_company_token(client)
    await _make_employee(client, {"Authorization": f"Bearer {admin_token}"})
    emp_login = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "emp@testco.com", "password": "emppass123"},
    )
    emp_token = emp_login.json()["access_token"]
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Read allowed.
    assert (await client.get("/api/v1/company/profile", headers=emp_headers)).status_code == 200
    # Write forbidden.
    resp = await client.put("/api/v1/company/profile", headers=emp_headers, json={"legal_name": "X"})
    assert resp.status_code == 403


# ============================ Logo ============================


@pytest.mark.asyncio
async def test_logo_upload_download_roundtrip(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    h = {"Authorization": f"Bearer {token}"}

    up = await client.post(
        "/api/v1/company/profile/logo",
        headers=h,
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert up.status_code == 200
    assert up.json()["has_logo"] is True

    down = await client.get("/api/v1/company/profile/logo", headers=h)
    assert down.status_code == 200
    assert down.headers["content-type"].startswith("image/png")
    assert down.content == PNG_BYTES  # encrypt/decrypt round-trip


@pytest.mark.asyncio
async def test_logo_wrong_type_415(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.post(
        "/api/v1/company/profile/logo",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("x.gif", b"GIF89a", "image/gif")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_get_logo_when_none_404(client: AsyncClient):
    await create_test_company(client)
    token = await get_company_token(client)
    resp = await client.get("/api/v1/company/profile/logo", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_logo_employee_forbidden(client: AsyncClient):
    await create_test_company(client)
    admin_token = await get_company_token(client)
    await _make_employee(client, {"Authorization": f"Bearer {admin_token}"})
    emp_login = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "emp@testco.com", "password": "emppass123"},
    )
    emp_headers = {"Authorization": f"Bearer {emp_login.json()['access_token']}"}
    resp = await client.post(
        "/api/v1/company/profile/logo",
        headers=emp_headers,
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 403


# ============================ Rate limiting ============================


@pytest.mark.asyncio
async def test_login_rate_limit_429(client: AsyncClient):
    await create_test_company(client)
    # Default limit is 10 per window; the 11th attempt should be throttled.
    statuses = []
    for _ in range(12):
        r = await client.post(
            "/api/v1/auth/company/login",
            json={"email": "admin@testco.com", "password": "wrongpass"},
        )
        statuses.append(r.status_code)
    assert 429 in statuses
    assert statuses.count(401) == 10
