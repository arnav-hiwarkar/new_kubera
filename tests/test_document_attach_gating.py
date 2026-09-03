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

    # 1. No docvault module at all -> 403
    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, no_docvault_user, document.id)
    assert exc_info.value.status_code == 403
    assert "docvault module" in exc_info.value.detail

    # 2. Has docvault module, but the bucket is restricted and ungranted -> 403
    with pytest.raises(Exception) as exc_info:
        await assert_document_attachable(db, with_docvault_user, document.id)
    assert exc_info.value.status_code == 403
    assert "access to this document" in exc_info.value.detail

    # 3. Admin bypasses both checks regardless of grants -> success
    result = await assert_document_attachable(db, admin, document.id)
    assert result.id == document.id

    # 4. Grant bucket access -> now succeeds for non-admin employee
    db.add(BucketAccessGrant(bucket_id=bucket.id, company_user_id=with_docvault_user.id))
    await db.commit()
    result = await assert_document_attachable(db, with_docvault_user, document.id)
    assert result.id == document.id


@pytest.mark.asyncio
async def test_assert_document_attachable_wrong_company_404(client: AsyncClient, db):
    """Tenant isolation: A document belonging to a different company must 404, not leak existence."""
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


async def _leaf_category(client: AsyncClient, admin_headers: dict) -> dict:
    resp = await client.post(
        "/api/v1/asset-masters/categories", json={"name": "Plant & Machinery"}, headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
    parent = resp.json()
    sub_resp = await client.post(
        "/api/v1/asset-masters/categories",
        json={"name": "Machines", "parent_id": parent["id"]},
        headers=admin_headers,
    )
    assert sub_resp.status_code == 201, sub_resp.text
    return sub_resp.json()


async def _upload_docvault_document(
    client: AsyncClient, headers: dict, title: str, bucket_id: str | None = None
) -> str:
    data = {"title": title}
    if bucket_id:
        data["bucket_id"] = bucket_id
    files = {"file": (f"{title}.txt", b"contents", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data=data, files=files, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _restrict_bucket(client: AsyncClient, admin_headers: dict, name: str, allowed_user_ids: list[str]) -> str:
    resp = await client.post("/api/v1/docvault/buckets", json={"name": name}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    bucket_id = resp.json()["id"]
    patch = await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": allowed_user_ids},
        headers=admin_headers,
    )
    assert patch.status_code == 200, patch.text
    return bucket_id


@pytest.mark.asyncio
async def test_attach_asset_document_requires_docvault_module(client: AsyncClient):
    await create_test_company(client, email="asset-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='asset-admin@testco.com')}"}
    category = await _leaf_category(client, admin_headers)
    document_id = await _upload_docvault_document(client, admin_headers, "Invoice")

    quick_add = await client.post(
        "/api/v1/assets/quick-add",
        json={"asset_name": "Laptop", "category_id": category["id"], "quantity": 1},
        headers=admin_headers,
    )
    assert quick_add.status_code == 201, quick_add.text
    asset_id = quick_add.json()["first_asset_id"]

    await _make_employee(client, admin_headers, "assets-only@testco.com", ["assets"])
    assets_only_headers = await _login_headers(client, "assets-only@testco.com")

    resp = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": document_id, "doc_role": "asset_photo"},
        headers=assets_only_headers,
    )
    assert resp.status_code == 403, resp.text
    assert "docvault module" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_attach_asset_document_requires_bucket_access(client: AsyncClient):
    await create_test_company(client, email="asset-admin2@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='asset-admin2@testco.com')}"}
    category = await _leaf_category(client, admin_headers)

    quick_add = await client.post(
        "/api/v1/assets/quick-add",
        json={"asset_name": "Laptop", "category_id": category["id"], "quantity": 1},
        headers=admin_headers,
    )
    asset_id = quick_add.json()["first_asset_id"]

    scoped = await _make_employee(client, admin_headers, "scoped@testco.com", ["assets", "docvault"])
    scoped_headers = await _login_headers(client, "scoped@testco.com")

    restricted_bucket_id = await _restrict_bucket(client, admin_headers, "Admin Only", [])
    document_id = await _upload_docvault_document(client, admin_headers, "Confidential", restricted_bucket_id)

    denied = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": document_id, "doc_role": "asset_photo"},
        headers=scoped_headers,
    )
    assert denied.status_code == 403, denied.text
    assert "access to this document" in denied.json()["detail"]

    # Grant bucket access -> attach now succeeds
    scoped_user_id = scoped["id"]
    grant = await client.patch(
        f"/api/v1/docvault/buckets/{restricted_bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [scoped_user_id]},
        headers=admin_headers,
    )
    assert grant.status_code == 200, grant.text

    allowed = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": document_id, "doc_role": "asset_photo"},
        headers=scoped_headers,
    )
    assert allowed.status_code == 201, allowed.text
    link_id = allowed.json()["id"]

    # Invariant 1: Download stays permissive for assets-only user with 0 DocVault access
    await _make_employee(client, admin_headers, "download-only@testco.com", ["assets"])
    download_only_headers = await _login_headers(client, "download-only@testco.com")
    stream = await client.get(f"/api/v1/asset-documents/{link_id}/thumbnail", headers=download_only_headers)
    assert stream.status_code == 200, stream.text


@pytest.mark.asyncio
async def test_attach_asset_document_anti_tamper_and_tenant_isolation(client: AsyncClient, db):
    """Tampered request checks: non-existent UUID -> 404; cross-tenant doc -> 404; malformed UUID -> 422."""
    await create_test_company(client, email="tamper-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='tamper-admin@testco.com')}"}
    category = await _leaf_category(client, admin_headers)
    quick_add = await client.post(
        "/api/v1/assets/quick-add",
        json={"asset_name": "Tamper Asset", "category_id": category["id"], "quantity": 1},
        headers=admin_headers,
    )
    asset_id = quick_add.json()["first_asset_id"]

    # 1. Non-existent UUID
    fake_id = str(uuid.uuid4())
    resp_fake = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": fake_id, "doc_role": "asset_photo"},
        headers=admin_headers,
    )
    assert resp_fake.status_code == 404

    # 2. Malformed UUID
    resp_malformed = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": "not-a-valid-uuid", "doc_role": "asset_photo"},
        headers=admin_headers,
    )
    assert resp_malformed.status_code == 422

    # 3. Cross-tenant document
    await create_test_company(client, name="OtherCo2", email="other2@testco.com")
    other_admin = await _user_by_email(db, "other2@testco.com")
    other_doc = Document(company_id=other_admin.company_id, title="OtherCo Doc", created_by=other_admin.id)
    db.add(other_doc)
    await db.commit()
    await db.refresh(other_doc)

    resp_cross = await client.post(
        f"/api/v1/assets/{asset_id}/documents",
        json={"document_id": str(other_doc.id), "doc_role": "asset_photo"},
        headers=admin_headers,
    )
    assert resp_cross.status_code == 404


async def _create_engagement_with_accepted_auditor(client: AsyncClient, co_headers: dict, aud_email: str) -> tuple[str, dict]:
    from tests.conftest import create_test_auditor, get_auditor_token

    eng_resp = await client.post("/api/v1/auditease/engagements", json={"period_label": "FY24"}, headers=co_headers)
    assert eng_resp.status_code == 201, eng_resp.text
    engagement_id = eng_resp.json()["id"]

    await create_test_auditor(client, email=aud_email, password="Valid1!Pass")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email=aud_email, password='Valid1!Pass')}"}

    invite = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/auditors/invite",
        json={"email": aud_email},
        headers=co_headers,
    )
    assert invite.status_code in (200, 201), invite.text
    accept = await client.post(f"/api/v1/auditor/engagements/{engagement_id}/accept", headers=aud_headers)
    assert accept.status_code == 200, accept.text
    return engagement_id, aud_headers


@pytest.mark.asyncio
async def test_add_query_message_attach_requires_docvault_module(client: AsyncClient):
    await create_test_company(client, email="ae-admin@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='ae-admin@testco.com')}"}
    engagement_id, aud_headers = await _create_engagement_with_accepted_auditor(
        client, admin_headers, "ae-auditor@aud.com"
    )
    query_resp = await client.post(
        f"/api/v1/auditor/engagements/{engagement_id}/queries",
        data={"initial_message": "Please clarify"},
        headers=aud_headers,
    )
    assert query_resp.status_code in (200, 201), query_resp.text
    query_id = query_resp.json()["id"]

    document_id = await _upload_docvault_document(client, admin_headers, "Report")

    await _make_employee(client, admin_headers, "ae-only@testco.com", ["auditease"])
    auditease_only_headers = await _login_headers(client, "ae-only@testco.com")

    resp = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/queries/{query_id}/messages",
        data={"text": "See attached", "attached_document_id": document_id},
        headers=auditease_only_headers,
    )
    assert resp.status_code == 403, resp.text
    assert "docvault module" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_query_attachment_download_permissive_for_module_scoped_user(client: AsyncClient):
    """Once attached, auditease-scoped company user can download via the dedicated endpoint
    with zero docvault access; generic docvault download endpoint continues to 403."""
    await create_test_company(client, email="ae-admin2@testco.com")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='ae-admin2@testco.com')}"}
    engagement_id, aud_headers = await _create_engagement_with_accepted_auditor(
        client, admin_headers, "ae-auditor2@aud.com"
    )
    query_resp = await client.post(
        f"/api/v1/auditor/engagements/{engagement_id}/queries",
        data={"initial_message": "Please clarify"},
        headers=aud_headers,
    )
    assert query_resp.status_code in (200, 201), query_resp.text
    query_id = query_resp.json()["id"]
    document_id = await _upload_docvault_document(client, admin_headers, "Report2")

    attach = await client.post(
        f"/api/v1/auditease/engagements/{engagement_id}/queries/{query_id}/messages",
        data={"text": "See attached", "attached_document_id": document_id},
        headers=admin_headers,
    )
    assert attach.status_code == 200, attach.text

    await _make_employee(client, admin_headers, "ae-viewer@testco.com", ["auditease"])
    auditease_only_headers = await _login_headers(client, "ae-viewer@testco.com")

    # Dedicated auditease download route succeeds
    new_route = await client.get(f"/api/v1/auditease/documents/{document_id}/download", headers=auditease_only_headers)
    assert new_route.status_code == 200, new_route.text

    # Metadata route succeeds
    meta_route = await client.get(f"/api/v1/auditease/documents/{document_id}", headers=auditease_only_headers)
    assert meta_route.status_code == 200, meta_route.text

    # Generic docvault route rejects
    generic_route = await client.get(f"/api/v1/docvault/documents/{document_id}/download", headers=auditease_only_headers)
    assert generic_route.status_code == 403, generic_route.text


@pytest.mark.asyncio
async def test_auditease_documents_unauthenticated_401(client: AsyncClient):
    """Invariant 4: Pre-auth requests reject with 401 or 403."""
    random_id = uuid.uuid4()
    resp1 = await client.get(f"/api/v1/auditease/documents/{random_id}")
    assert resp1.status_code in (401, 403), resp1.text

    resp2 = await client.get(f"/api/v1/auditease/documents/{random_id}/download")
    assert resp2.status_code in (401, 403), resp2.text


@pytest.mark.asyncio
async def test_auditease_documents_tenant_isolation_404(client: AsyncClient, db):
    """Invariant 3: Accessing another company's document via AuditEase returns 404."""
    await create_test_company(client, email="co1-admin@testco.com")
    co1_headers = {"Authorization": f"Bearer {await get_company_token(client, email='co1-admin@testco.com')}"}

    await create_test_company(client, name="OtherCo3", email="co3-admin@testco.com")
    co3_admin = await _user_by_email(db, "co3-admin@testco.com")
    other_doc = Document(company_id=co3_admin.company_id, title="OtherCo Doc", created_by=co3_admin.id)
    db.add(other_doc)
    await db.commit()
    await db.refresh(other_doc)

    resp = await client.get(f"/api/v1/auditease/documents/{other_doc.id}", headers=co1_headers)
    assert resp.status_code == 404, resp.text

    resp_dl = await client.get(f"/api/v1/auditease/documents/{other_doc.id}/download", headers=co1_headers)
    assert resp_dl.status_code == 404, resp_dl.text


