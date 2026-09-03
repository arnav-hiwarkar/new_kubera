import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import CompanyUser
from app.models.docvault import Bucket, BucketAccessGrant, BucketVisibility, Document
from app.services.bucket_access import assert_document_attachable
from tests.conftest import create_test_company, get_company_token


async def _make_employee(client: AsyncClient, admin_headers: dict, email: str, modules: list[str]) -> dict:
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": email,
            "password": "Valid1!Pass",
            "full_name": email.split("@")[0],
            "role": "employee",
            "accessible_modules": modules,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _user_by_email(db, email: str) -> CompanyUser:
    result = await db.execute(select(CompanyUser).where(CompanyUser.email == email))
    return result.scalar_one()


async def _login_headers(client: AsyncClient, email: str, password: str = "Valid1!Pass") -> dict:
    resp = await client.post("/api/v1/auth/company/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_assert_document_attachable_matrix(client: AsyncClient, db):
    """admin bypass; no docvault module -> 403; docvault but wrong bucket -> 403;
    docvault + bucket access -> returns the document."""
    await create_test_company(client, email="attach-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='attach-admin@testco.com')}"}

    await _make_employee(client, admin_headers, "no-docvault@testco.com", ["assets"])
    await _make_employee(client, admin_headers, "with-docvault@testco.com", ["assets", "docvault"])

    admin = await _user_by_email(db, "attach-admin@testco.com")
    no_docvault_user = await _user_by_email(db, "no-docvault@testco.com")
    with_docvault_user = await _user_by_email(db, "with-docvault@testco.com")

    bucket = Bucket(
        company_id=admin.company_id,
        name="Restricted Bucket",
        visibility=BucketVisibility.restricted,
        created_by=admin.id,
    )
    db.add(bucket)
    await db.flush()

    document = Document(
        company_id=admin.company_id,
        bucket_id=bucket.id,
        title="Secret",
        created_by=admin.id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # No docvault module at all.
    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, no_docvault_user, document.id)
    assert exc_info.value.status_code == 403
    assert "docvault module" in exc_info.value.detail

    # Has docvault module, but the bucket is restricted and ungranted.
    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, with_docvault_user, document.id)
    assert exc_info.value.status_code == 403
    assert "access to this document" in exc_info.value.detail

    # Admin bypasses both checks regardless of grants.
    result = await assert_document_attachable(db, admin, document.id)
    assert result.id == document.id

    # Grant bucket access -> now succeeds for the non-admin too.
    db.add(BucketAccessGrant(bucket_id=bucket.id, company_user_id=with_docvault_user.id))
    await db.commit()
    result = await assert_document_attachable(db, with_docvault_user, document.id)
    assert result.id == document.id


@pytest.mark.asyncio
async def test_assert_document_attachable_wrong_company_404(client: AsyncClient, db):
    """A document belonging to a different company must 404, not leak existence."""
    await create_test_company(client, email="companyA@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='companyA@testco.com')}"}
    await _make_employee(client, admin_headers, "userA@testco.com", ["docvault"])
    user_a = await _user_by_email(db, "userA@testco.com")

    await create_test_company(client, name="OtherCo", email="admin@otherco.com")
    other_admin = await _user_by_email(db, "admin@otherco.com")
    other_doc = Document(company_id=other_admin.company_id, title="Not yours", created_by=other_admin.id)
    db.add(other_doc)
    await db.commit()
    await db.refresh(other_doc)

    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, user_a, other_doc.id)
    assert exc_info.value.status_code == 404
