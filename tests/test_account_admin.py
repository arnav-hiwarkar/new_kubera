import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    INTERNAL_API_KEY, init_company, create_test_company, get_company_token,
    create_test_auditor, get_auditor_token,
)
from app.models.company import CompanyUser
from app.models.docvault import Bucket
from app.services import account_admin


async def _create_user(client, admin_token, *, email, password, full_name="Emp User", role="employee"):
    resp = await client.post(
        "/api/v1/users",
        json={"email": email, "password": password, "full_name": full_name, "role": role},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Soft-delete user -----------------------------------------------------------

@pytest.mark.asyncio
async def test_soft_delete_user_disables_login_frees_email_keeps_row(
    client: AsyncClient, db: AsyncSession
):
    """Deleting a user must succeed even when they own data, disable their login,
    free their email for reuse, and keep the row so their name still resolves."""
    await create_test_company(client, name="SoftCo", email="admin@softco.com")
    admin_token = await get_company_token(client, email="admin@softco.com")

    emp = await _create_user(client, admin_token, email="emp@softco.com", password="emppass123")
    emp_id = uuid.UUID(emp["id"])
    company_id = uuid.UUID(emp["company_id"])

    # The employee can log in before deletion.
    login = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "emp@softco.com", "password": "emppass123"},
    )
    assert login.status_code == 200

    # Attach work the employee "owns": a bucket whose created_by FK (no ondelete)
    # would make a hard delete fail with a 409.
    db.add(Bucket(company_id=company_id, name="Emp Bucket", created_by=emp_id))
    await db.commit()

    # Soft-delete via the admin endpoint — must succeed despite the owned bucket.
    resp = await client.delete(
        f"/api/v1/users/{emp_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204, resp.text

    # Login is now blocked.
    login = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "emp@softco.com", "password": "emppass123"},
    )
    assert login.status_code == 401

    # The row survives: name intact, marked deleted, email freed to the sentinel.
    row = (await db.execute(select(CompanyUser).where(CompanyUser.id == emp_id))).scalar_one()
    assert row.is_active is False
    assert row.deleted_at is not None
    assert row.full_name == "Emp User"
    assert row.email == f"deleted+{emp_id}@deleted.invalid"

    # The attached bucket still points at the surviving row (name still resolvable).
    bucket = (await db.execute(select(Bucket).where(Bucket.created_by == emp_id))).scalar_one()
    assert bucket.created_by == emp_id

    # The original email is free — a brand-new user can reuse it.
    again = await _create_user(client, admin_token, email="emp@softco.com", password="newpass123", full_name="New Hire")
    assert again["id"] != emp["id"]


# --- Password reset -------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_password_company_user(client: AsyncClient, db: AsyncSession):
    await create_test_company(client, name="PwCo", email="admin@pwco.com", password="oldpass123")

    matches = await account_admin.find_accounts(db, "admin@pwco.com")
    assert len(matches) == 1 and matches[0]["principal_type"] == account_admin.COMPANY_USER
    await account_admin.set_password(db, matches[0]["principal_type"], matches[0]["id"], "brandnew123")
    await db.commit()

    # New password works; old one does not.
    ok = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "admin@pwco.com", "password": "brandnew123"},
    )
    assert ok.status_code == 200
    bad = await client.post(
        "/api/v1/auth/company/login",
        json={"email": "admin@pwco.com", "password": "oldpass123"},
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_set_password_auditor(client: AsyncClient, db: AsyncSession):
    await create_test_auditor(client, email="aud@x.com", password="oldpass123")

    matches = await account_admin.find_accounts(db, "aud@x.com")
    assert len(matches) == 1 and matches[0]["principal_type"] == account_admin.AUDITOR
    await account_admin.set_password(db, matches[0]["principal_type"], matches[0]["id"], "brandnew123")
    await db.commit()

    ok = await client.post(
        "/api/v1/auth/auditor/login",
        json={"email": "aud@x.com", "password": "brandnew123"},
    )
    assert ok.status_code == 200


# --- Archive company ------------------------------------------------------------

@pytest.mark.asyncio
async def test_archive_company_disables_logins_and_frees_name_and_email(client: AsyncClient):
    data = await create_test_company(client, name="ArchCo", email="arch@x.com", password="adminpass123")
    company_id = data["company"]["id"]
    admin_token = await get_company_token(client, email="arch@x.com", password="adminpass123")
    await _create_user(client, admin_token, email="u2@archco.com", password="u2pass123")

    # Archive via the internal operator endpoint.
    resp = await client.request(
        "DELETE",
        f"/api/v1/auth/companies/{company_id}",
        json={"confirm_name": "ArchCo"},
        headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
    )
    assert resp.status_code == 204, resp.text

    # Every login into the archived company is blocked.
    for email, pw in (("arch@x.com", "adminpass123"), ("u2@archco.com", "u2pass123")):
        login = await client.post("/api/v1/auth/company/login", json={"email": email, "password": pw})
        assert login.status_code == 401, f"{email} should not be able to log in"

    # The company shows up as archived in the operator listing.
    listing = await client.get(
        "/api/v1/auth/companies", headers={"X-Internal-Api-Key": INTERNAL_API_KEY}
    )
    assert listing.status_code == 200
    entry = next(c for c in listing.json() if c["id"] == company_id)
    assert entry["archived"] is True

    # A fresh company can reuse the same name AND admin email.
    reuse = await init_company(client, name="ArchCo", email="arch@x.com")
    assert reuse["company"]["id"] != company_id


@pytest.mark.asyncio
async def test_archive_company_twice_conflicts(client: AsyncClient):
    data = await create_test_company(client, name="TwiceCo", email="twice@x.com")
    company_id = data["company"]["id"]
    headers = {"X-Internal-Api-Key": INTERNAL_API_KEY}

    first = await client.request(
        "DELETE", f"/api/v1/auth/companies/{company_id}", json={"confirm_name": "TwiceCo"}, headers=headers
    )
    assert first.status_code == 204
    second = await client.request(
        "DELETE", f"/api/v1/auth/companies/{company_id}", json={"confirm_name": "TwiceCo"}, headers=headers
    )
    assert second.status_code == 409
