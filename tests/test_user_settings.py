import io
import uuid
import pytest
from httpx import AsyncClient
from tests.conftest import create_test_company, get_company_token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# 1x1 PNG magic bytes
TINY_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

# Tiny JPEG magic bytes
TINY_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xbf\x00\xff\xd9"

# Tiny WEBP magic bytes
TINY_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8L\x0e\x00\x00\x00/\x00\x00\x00\x00\x00\x810\x00\x00\x00\x00\x00"


@pytest.mark.asyncio
async def test_password_change_success(client: AsyncClient):
    await create_test_company(client, email="pwd-user1@test.com", password="Password123!")
    token = await get_company_token(client, email="pwd-user1@test.com", password="Password123!")
    headers = _headers(token)

    # Change password to new valid password
    res = await client.post(
        "/api/v1/users/me/change-password",
        json={
            "old_password": "Password123!",
            "new_password": "NewSecret@2026",
            "confirm_password": "NewSecret@2026",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True

    # Verify old password no longer works
    login_old = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "pwd-user1@test.com", "password": "Password123!"},
    )
    assert login_old.status_code == 401

    # Verify new password works
    login_new = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "pwd-user1@test.com", "password": "NewSecret@2026"},
    )
    assert login_new.status_code == 200
    assert "access_token" in login_new.json()


@pytest.mark.asyncio
async def test_password_change_wrong_old_password(client: AsyncClient):
    await create_test_company(client, email="pwd-wrong-old@test.com", password="Password123!")
    token = await get_company_token(client, email="pwd-wrong-old@test.com", password="Password123!")
    headers = _headers(token)

    res = await client.post(
        "/api/v1/users/me/change-password",
        json={
            "old_password": "IncorrectPassword999!",
            "new_password": "NewSecret@2026",
            "confirm_password": "NewSecret@2026",
        },
        headers=headers,
    )
    assert res.status_code == 400
    assert "Current password is incorrect" in res.json()["detail"]


@pytest.mark.asyncio
async def test_password_change_same_as_old(client: AsyncClient):
    await create_test_company(client, email="pwd-same@test.com", password="Password123!")
    token = await get_company_token(client, email="pwd-same@test.com", password="Password123!")
    headers = _headers(token)

    res = await client.post(
        "/api/v1/users/me/change-password",
        json={
            "old_password": "Password123!",
            "new_password": "Password123!",
            "confirm_password": "Password123!",
        },
        headers=headers,
    )
    assert res.status_code == 400
    assert "different from your current password" in res.json()["detail"]


@pytest.mark.asyncio
async def test_password_change_mismatched_confirm(client: AsyncClient):
    await create_test_company(client, email="pwd-mismatch@test.com", password="Password123!")
    token = await get_company_token(client, email="pwd-mismatch@test.com", password="Password123!")
    headers = _headers(token)

    res = await client.post(
        "/api/v1/users/me/change-password",
        json={
            "old_password": "Password123!",
            "new_password": "NewSecret@2026",
            "confirm_password": "DifferentSecret@2026",
        },
        headers=headers,
    )
    assert res.status_code == 400
    assert "do not match" in res.json()["detail"]


@pytest.mark.asyncio
async def test_password_change_complexity_enforcement(client: AsyncClient):
    await create_test_company(client, email="pwd-complex@test.com", password="Password123!")
    token = await get_company_token(client, email="pwd-complex@test.com", password="Password123!")
    headers = _headers(token)

    # Missing uppercase
    r1 = await client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "Password123!", "new_password": "password123!", "confirm_password": "password123!"},
        headers=headers,
    )
    assert r1.status_code == 400
    assert "uppercase" in r1.json()["detail"]

    # Missing lowercase
    r2 = await client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "Password123!", "new_password": "PASSWORD123!", "confirm_password": "PASSWORD123!"},
        headers=headers,
    )
    assert r2.status_code == 400
    assert "lowercase" in r2.json()["detail"]

    # Missing number
    r3 = await client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "Password123!", "new_password": "PasswordSpecial!", "confirm_password": "PasswordSpecial!"},
        headers=headers,
    )
    assert r3.status_code == 400
    assert "number" in r3.json()["detail"]

    # Missing special character
    r4 = await client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "Password123!", "new_password": "Password1234", "confirm_password": "Password1234"},
        headers=headers,
    )
    assert r4.status_code == 400
    assert "special character" in r4.json()["detail"]

    # Too short (< 8 chars)
    r5 = await client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "Password123!", "new_password": "Pass1!", "confirm_password": "Pass1!"},
        headers=headers,
    )
    assert r5.status_code in (400, 422)



@pytest.mark.asyncio
async def test_password_change_permission_denied(client: AsyncClient):
    await create_test_company(client, email="admin-toggle@test.com", password="Password123!")
    admin_token = await get_company_token(client, email="admin-toggle@test.com", password="Password123!")
    admin_headers = _headers(admin_token)

    # Create employee with can_change_password=False
    emp_create = await client.post(
        "/api/v1/users",
        json={
            "email": "noperm-emp@test.com",
            "password": "Password123!",
            "full_name": "No Perm Employee",
            "role": "employee",
            "can_change_password": False,
        },
        headers=admin_headers,
    )
    assert emp_create.status_code == 201
    assert emp_create.json()["can_change_password"] is False

    emp_token = await get_company_token(client, email="noperm-emp@test.com", password="Password123!")
    emp_headers = _headers(emp_token)

    # Employee tries to change password -> 403 Forbidden
    res = await client.post(
        "/api/v1/users/me/change-password",
        json={
            "old_password": "Password123!",
            "new_password": "NewSecret@2026",
            "confirm_password": "NewSecret@2026",
        },
        headers=emp_headers,
    )
    assert res.status_code == 403
    assert "permission" in res.json()["detail"]

    # Admin updates can_change_password=True
    emp_id = emp_create.json()["id"]
    emp_update = await client.patch(
        f"/api/v1/users/{emp_id}",
        json={"can_change_password": True},
        headers=admin_headers,
    )
    assert emp_update.status_code == 200
    assert emp_update.json()["can_change_password"] is True

    # Employee can now change password
    res2 = await client.post(
        "/api/v1/users/me/change-password",
        json={
            "old_password": "Password123!",
            "new_password": "NewSecret@2026",
            "confirm_password": "NewSecret@2026",
        },
        headers=emp_headers,
    )
    assert res2.status_code == 200


@pytest.mark.asyncio
async def test_password_change_30_day_cooldown(client: AsyncClient):
    await create_test_company(client, email="pwd-cooldown@test.com", password="Password123!")
    token = await get_company_token(client, email="pwd-cooldown@test.com", password="Password123!")
    headers = _headers(token)

    # First change succeeds
    r1 = await client.post(
        "/api/v1/users/me/change-password",
        json={
            "old_password": "Password123!",
            "new_password": "NewSecret@2026",
            "confirm_password": "NewSecret@2026",
        },
        headers=headers,
    )
    assert r1.status_code == 200

    # Immediate second change returns 429 Too Many Requests
    r2 = await client.post(
        "/api/v1/users/me/change-password",
        json={
            "old_password": "NewSecret@2026",
            "new_password": "AnotherSecret@2026",
            "confirm_password": "AnotherSecret@2026",
        },
        headers=headers,
    )
    assert r2.status_code == 429
    assert "30 days" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_avatar_upload_success_and_streaming(client: AsyncClient):
    await create_test_company(client, email="avatar-user@test.com", password="Password123!")
    token = await get_company_token(client, email="avatar-user@test.com", password="Password123!")
    headers = _headers(token)

    # Upload valid PNG avatar
    files = {"file": ("avatar.png", io.BytesIO(TINY_PNG), "image/png")}
    upload_res = await client.post("/api/v1/users/me/avatar", files=files, headers=headers)
    assert upload_res.status_code == 200, upload_res.text
    user_data = upload_res.json()
    assert user_data["has_avatar"] is True
    assert user_data["avatar_updated_at"] is not None

    # Stream /me/avatar
    stream_res = await client.get("/api/v1/users/me/avatar", headers=headers)
    assert stream_res.status_code == 200
    assert stream_res.content == TINY_PNG
    assert stream_res.headers["content-type"] == "image/png"
    assert "nosniff" in stream_res.headers.get("x-content-type-options", "")
    assert "sandbox" in stream_res.headers.get("content-security-policy", "")

    # Stream /{user_id}/avatar
    user_id = user_data["id"]
    stream_id_res = await client.get(f"/api/v1/users/{user_id}/avatar", headers=headers)
    assert stream_id_res.status_code == 200
    assert stream_id_res.content == TINY_PNG


@pytest.mark.asyncio
async def test_avatar_upload_size_limit(client: AsyncClient):
    await create_test_company(client, email="avatar-size@test.com", password="Password123!")
    token = await get_company_token(client, email="avatar-size@test.com", password="Password123!")
    headers = _headers(token)

    # Oversized payload: 1.1 MB
    big_png = TINY_PNG + b"\x00" * (1100 * 1024)
    files = {"file": ("big.png", io.BytesIO(big_png), "image/png")}
    upload_res = await client.post("/api/v1/users/me/avatar", files=files, headers=headers)
    assert upload_res.status_code == 413
    assert "1 MB or smaller" in upload_res.json()["detail"]


@pytest.mark.asyncio
async def test_avatar_upload_invalid_magic_bytes(client: AsyncClient):
    await create_test_company(client, email="avatar-spoof@test.com", password="Password123!")
    token = await get_company_token(client, email="avatar-spoof@test.com", password="Password123!")
    headers = _headers(token)

    # Spoofed content: text claiming to be PNG
    fake_png = b"<html><body>Not an image</body></html>"
    files = {"file": ("avatar.png", io.BytesIO(fake_png), "image/png")}
    upload_res = await client.post("/api/v1/users/me/avatar", files=files, headers=headers)
    assert upload_res.status_code == 415
    assert "valid JPG, PNG, or WEBP" in upload_res.json()["detail"]


@pytest.mark.asyncio
async def test_avatar_upload_3_hour_cooldown(client: AsyncClient):
    await create_test_company(client, email="avatar-cooldown@test.com", password="Password123!")
    token = await get_company_token(client, email="avatar-cooldown@test.com", password="Password123!")
    headers = _headers(token)

    # First upload succeeds
    files1 = {"file": ("avatar.png", io.BytesIO(TINY_PNG), "image/png")}
    r1 = await client.post("/api/v1/users/me/avatar", files=files1, headers=headers)
    assert r1.status_code == 200

    # Immediate second upload returns 429
    files2 = {"file": ("avatar.jpg", io.BytesIO(TINY_JPEG), "image/jpeg")}
    r2 = await client.post("/api/v1/users/me/avatar", files=files2, headers=headers)
    assert r2.status_code == 429
    assert "3 hours" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_avatar_cross_tenant_isolation(client: AsyncClient):
    # Company A user
    await create_test_company(client, email="user-comp-a@test.com", password="Password123!")
    token_a = await get_company_token(client, email="user-comp-a@test.com", password="Password123!")
    headers_a = _headers(token_a)

    files = {"file": ("avatar.png", io.BytesIO(TINY_PNG), "image/png")}
    upload_a = await client.post("/api/v1/users/me/avatar", files=files, headers=headers_a)
    assert upload_a.status_code == 200
    user_a_id = upload_a.json()["id"]

    # Company B user
    await create_test_company(client, email="user-comp-b@test.com", password="Password123!")
    token_b = await get_company_token(client, email="user-comp-b@test.com", password="Password123!")
    headers_b = _headers(token_b)

    # User B tries to access User A's avatar -> 404 Not Found (tenant scoped)
    res = await client.get(f"/api/v1/users/{user_a_id}/avatar", headers=headers_b)
    assert res.status_code == 404
