import pytest
from httpx import AsyncClient
from app.models.docvault import Document, DocumentStatus
from tests.conftest import create_test_company, get_company_token


async def _create_member(
    client: AsyncClient,
    admin_headers: dict,
    email: str,
    password: str = "member1234",
    full_name: str = "Member User",
    role: str = "employee",
    modules: list[str] | None = None,
) -> str:
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": role,
            "accessible_modules": modules if modules is not None else ["docvault"],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_document_model_has_approval_fields():
    assert hasattr(Document, "approver_id")
    assert hasattr(Document, "approval_requested_at")
    assert hasattr(Document, "approved_at")
    assert hasattr(Document, "approval_notes")


@pytest.mark.asyncio
async def test_upload_with_approval_request_and_notification(client: AsyncClient):
    await create_test_company(client, name="ApproveCo", email="admin@approve.com", password="pass1234")
    admin_token = await get_company_token(client, email="admin@approve.com", password="pass1234")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Get admin user id
    me_resp = await client.get("/api/v1/users/me", headers=admin_headers)
    admin_id = me_resp.json()["id"]

    # Create member
    member_id = await _create_member(client, admin_headers, "member@approve.com", "pass1234", "Alice Smith", "employee", ["docvault"])
    member_token = await get_company_token(client, email="member@approve.com", password="pass1234")
    member_headers = {"Authorization": f"Bearer {member_token}"}

    # Member uploads document with approval request assigned to admin
    files = {"file": ("contract.pdf", b"pdf content", "application/pdf")}
    data = {
        "title": "Vendor Contract",
        "needs_approval": "true",
        "approver_id": admin_id,
        "is_editable": "true",
    }
    resp = await client.post("/api/v1/docvault/documents", data=data, files=files, headers=member_headers)
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["status"] == "pending_approval"
    assert doc["approver_id"] == admin_id
    assert doc["approver_name"] is not None
    assert doc["approval_requested_at"] is not None
    doc_id = doc["id"]

    # Verify admin received in-app notification
    notif_resp = await client.get("/api/v1/notifications", headers=admin_headers)
    assert notif_resp.status_code == 200
    notifs = notif_resp.json()
    assert any(n["type"] == "docvault.approval_requested" and n["payload"]["document_id"] == doc_id for n in notifs)


@pytest.mark.asyncio
async def test_ineligible_approver_rejected(client: AsyncClient):
    await create_test_company(client, name="CompanyA", email="adminA@test.com", password="pass1234")
    token_a = await get_company_token(client, email="adminA@test.com", password="pass1234")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    await create_test_company(client, name="CompanyB", email="adminB@test.com", password="pass1234")
    token_b = await get_company_token(client, email="adminB@test.com", password="pass1234")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    me_b = (await client.get("/api/v1/users/me", headers=headers_b)).json()["id"]

    # Member in Company A without docvault access
    no_vault_id = await _create_member(client, headers_a, "novault@test.com", "pass1234", "No Vault", "employee", ["assets"])

    # 1. Attacker attempts to assign approver from Company B
    files = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Test 1", "needs_approval": "true", "approver_id": me_b},
        files=files,
        headers=headers_a,
    )
    assert resp.status_code == 400
    assert "approver" in resp.json()["detail"].lower()

    # 2. Attacker attempts to assign approver without docvault module access
    files2 = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Test 2", "needs_approval": "true", "approver_id": no_vault_id},
        files=files2,
        headers=headers_a,
    )
    assert resp.status_code == 400
    assert "docvault access" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_restricted_bucket_approver_validation(client: AsyncClient):
    await create_test_company(client, name="BucketGuardCo", email="admin@bg.com", password="pass1234")
    admin_token = await get_company_token(client, email="admin@bg.com", password="pass1234")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    user1_id = await _create_member(client, admin_headers, "u1@bg.com", "pass1234", "User One", "employee", ["docvault"])
    user2_id = await _create_member(client, admin_headers, "u2@bg.com", "pass1234", "User Two", "employee", ["docvault"])

    # Create restricted bucket with access only to user1
    b_resp = await client.post("/api/v1/docvault/buckets", json={"name": "Restricted Secret"}, headers=admin_headers)
    bucket_id = b_resp.json()["id"]
    await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [user1_id]},
        headers=admin_headers,
    )

    # Admin tries to upload to restricted bucket with user2 (who has NO bucket access) as approver
    files = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Secret Doc", "bucket_id": bucket_id, "needs_approval": "true", "approver_id": user2_id},
        files=files,
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "access to this bucket" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_non_approver_authorization_guardrails(client: AsyncClient):
    await create_test_company(client, name="GuardCo", email="admin@gc.com", password="pass1234")
    admin_token = await get_company_token(client, email="admin@gc.com", password="pass1234")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@gc.com", "pass1234", "Uploader", "employee", ["docvault"])
    u2_id = await _create_member(client, admin_headers, "u2@gc.com", "pass1234", "Approver", "employee", ["docvault"])
    u3_id = await _create_member(client, admin_headers, "u3@gc.com", "pass1234", "Stranger", "employee", ["docvault"])

    t1 = await get_company_token(client, email="u1@gc.com", password="pass1234")
    t2 = await get_company_token(client, email="u2@gc.com", password="pass1234")
    t3 = await get_company_token(client, email="u3@gc.com", password="pass1234")
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}
    h3 = {"Authorization": f"Bearer {t3}"}

    # U1 uploads doc assigning U2 as approver
    files = {"file": ("spec.pdf", b"initial spec", "application/pdf")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Project Spec", "needs_approval": "true", "approver_id": u2_id},
        files=files,
        headers=h1,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    # 1. Stranger U3 attempts to approve -> 403 Forbidden
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"status": "verified"}, headers=h3)
    assert resp.status_code == 403

    # 2. Stranger U3 attempts to edit title during pending approval -> 409 Conflict
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"title": "Tampered Spec"}, headers=h3)
    assert resp.status_code == 409

    # 3. Stranger U3 attempts to upload new version -> 409 Conflict
    files2 = {"file": ("spec_v2.pdf", b"tampered v2", "application/pdf")}
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/versions", files=files2, headers=h3)
    assert resp.status_code == 409

    # 4. Assigned approver U2 approves document with notes -> 200 OK
    resp = await client.patch(
        f"/api/v1/docvault/documents/{doc_id}",
        json={"status": "verified", "approval_notes": "Approved after technical review"},
        headers=h2,
    )
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["status"] == "verified"
    assert doc["approved_at"] is not None
    assert doc["approval_notes"] == "Approved after technical review"

    # 5. Verify uploader U1 received notification of resolution
    notifs = (await client.get("/api/v1/notifications", headers=h1)).json()
    assert any(n["type"] == "docvault.approval_resolved" and n["payload"]["document_id"] == doc_id for n in notifs)


@pytest.mark.asyncio
async def test_admin_override_and_request_changes(client: AsyncClient):
    await create_test_company(client, name="OverrideCo", email="admin@ov.com", password="pass1234")
    admin_token = await get_company_token(client, email="admin@ov.com", password="pass1234")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@ov.com", "pass1234", "Uploader", "employee", ["docvault"])
    u2_id = await _create_member(client, admin_headers, "u2@ov.com", "pass1234", "Approver", "employee", ["docvault"])
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@ov.com', 'pass1234')}"}

    files = {"file": ("proposal.pdf", b"proposal data", "application/pdf")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Budget Proposal", "needs_approval": "true", "approver_id": u2_id},
        files=files,
        headers=h1,
    )
    doc_id = resp.json()["id"]

    # Admin overrides and requests changes (status: action_required)
    resp = await client.patch(
        f"/api/v1/docvault/documents/{doc_id}",
        json={"status": "action_required", "approval_notes": "Please include tax breakdown table"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["status"] == "action_required"
    assert doc["approval_notes"] == "Please include tax breakdown table"

    # Uploader sees notification
    notifs = (await client.get("/api/v1/notifications", headers=h1)).json()
    assert any(n["type"] == "docvault.approval_resolved" and n["payload"]["document_id"] == doc_id for n in notifs)


@pytest.mark.asyncio
async def test_final_document_lock_behavior(client: AsyncClient):
    await create_test_company(client, name="FinalCo", email="admin@final.com", password="pass1234")
    token = await get_company_token(client, email="admin@final.com", password="pass1234")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload with is_editable=False ("Final")
    files = {"file": ("final_policy.pdf", b"policy text", "application/pdf")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Company Policy 2026", "is_editable": "false"},
        files=files,
        headers=headers,
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["is_editable"] is False
    doc_id = doc["id"]

    # Attempt to rename or change tags -> 409
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"title": "Changed Title"}, headers=headers)
    assert resp.status_code == 409

    # Attempt to upload version -> 409
    files2 = {"file": ("v2.pdf", b"v2 data", "application/pdf")}
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/versions", files=files2, headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_pending_my_approval_filter(client: AsyncClient):
    await create_test_company(client, name="FilterCo", email="admin@ft.com", password="pass1234")
    admin_token = await get_company_token(client, email="admin@ft.com", password="pass1234")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = (await client.get("/api/v1/users/me", headers=admin_headers)).json()["id"]

    u1_id = await _create_member(client, admin_headers, "u1@ft.com", "pass1234", "U1", "employee", ["docvault"])
    u2_id = await _create_member(client, admin_headers, "u2@ft.com", "pass1234", "U2", "employee", ["docvault"])
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@ft.com', 'pass1234')}"}

    # U1 uploads doc 1 assigned to admin
    f1 = {"file": ("d1.txt", b"d1", "text/plain")}
    await client.post("/api/v1/docvault/documents", data={"title": "Doc for Admin", "needs_approval": "true", "approver_id": admin_id}, files=f1, headers=h1)

    # U1 uploads doc 2 assigned to u2
    f2 = {"file": ("d2.txt", b"d2", "text/plain")}
    await client.post("/api/v1/docvault/documents", data={"title": "Doc for U2", "needs_approval": "true", "approver_id": u2_id}, files=f2, headers=h1)

    # Admin queries pending_my_approval
    resp = await client.get("/api/v1/docvault/documents?pending_my_approval=true", headers=admin_headers)
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 1
    assert docs[0]["title"] == "Doc for Admin"
