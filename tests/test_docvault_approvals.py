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
            "accessible_modules": modules if modules is not None else ["docvault", "notifications"],
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
    await create_test_company(client, name="ApproveCo", email="admin@approve.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@approve.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Get admin user id
    me_resp = await client.get("/api/v1/users/me", headers=admin_headers)
    admin_id = me_resp.json()["id"]

    # Create member
    member_id = await _create_member(client, admin_headers, "member@approve.com", "Valid1!Pass", "Alice Smith", "employee", ["docvault", "notifications"])
    member_token = await get_company_token(client, email="member@approve.com", password="Valid1!Pass")
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

    # Admin reviews and approves using POST /review
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/review", json={"decision": "verified", "approval_notes": "Looks good"}, headers=admin_headers)
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["status"] == "verified"
    assert doc["approved_at"] is not None
    assert doc["approval_notes"] == "Looks good"


@pytest.mark.asyncio
async def test_ineligible_approver_rejected(client: AsyncClient):
    await create_test_company(client, name="CompanyA", email="adminA@test.com", password="Valid1!Pass")
    token_a = await get_company_token(client, email="adminA@test.com", password="Valid1!Pass")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    await create_test_company(client, name="CompanyB", email="adminB@test.com", password="Valid1!Pass")
    token_b = await get_company_token(client, email="adminB@test.com", password="Valid1!Pass")
    headers_b = {"Authorization": f"Bearer {token_b}"}
    me_b = (await client.get("/api/v1/users/me", headers=headers_b)).json()["id"]

    # Member in Company A without docvault access
    no_vault_id = await _create_member(client, headers_a, "novault@test.com", "Valid1!Pass", "No Vault", "employee", ["assets"])

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
    await create_test_company(client, name="BucketGuardCo", email="admin@bg.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@bg.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    user1_id = await _create_member(client, admin_headers, "u1@bg.com", "Valid1!Pass", "User One", "employee", ["docvault", "notifications"])
    user2_id = await _create_member(client, admin_headers, "u2@bg.com", "Valid1!Pass", "User Two", "employee", ["docvault", "notifications"])

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
    await create_test_company(client, name="GuardCo", email="admin@gc.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@gc.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@gc.com", "Valid1!Pass", "Uploader", "employee", ["docvault", "notifications"])
    u2_id = await _create_member(client, admin_headers, "u2@gc.com", "Valid1!Pass", "Approver", "employee", ["docvault", "notifications"])
    u3_id = await _create_member(client, admin_headers, "u3@gc.com", "Valid1!Pass", "Stranger", "employee", ["docvault", "notifications"])

    t1 = await get_company_token(client, email="u1@gc.com", password="Valid1!Pass")
    t2 = await get_company_token(client, email="u2@gc.com", password="Valid1!Pass")
    t3 = await get_company_token(client, email="u3@gc.com", password="Valid1!Pass")
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
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/review", json={"decision": "verified"}, headers=h3)
    assert resp.status_code == 403

    # 2. Stranger U3 attempts to edit title during pending approval -> 403 Forbidden
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"title": "Tampered Spec"}, headers=h3)
    assert resp.status_code == 403

    # 3. Stranger U3 attempts to upload new version -> 403 Forbidden
    files2 = {"file": ("spec_v2.pdf", b"tampered v2", "application/pdf")}
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/versions", files=files2, headers=h3)
    assert resp.status_code == 403

    # 4. Assigned approver U2 approves document with notes -> 200 OK
    resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "verified", "approval_notes": "Approved after technical review"},
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
    await create_test_company(client, name="OverrideCo", email="admin@ov.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@ov.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@ov.com", "Valid1!Pass", "Uploader", "employee", ["docvault", "notifications"])
    u2_id = await _create_member(client, admin_headers, "u2@ov.com", "Valid1!Pass", "Approver", "employee", ["docvault", "notifications"])
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@ov.com', 'Valid1!Pass')}"}

    files = {"file": ("proposal.pdf", b"proposal data", "application/pdf")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Budget Proposal", "needs_approval": "true", "approver_id": u2_id},
        files=files,
        headers=h1,
    )
    doc_id = resp.json()["id"]

    # Admin overrides and requests changes (status: action_required)
    resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "action_required", "approval_notes": "Please include tax breakdown table"},
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
    await create_test_company(client, name="FinalCo", email="admin@final.com", password="Valid1!Pass")
    token = await get_company_token(client, email="admin@final.com", password="Valid1!Pass")
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
    await create_test_company(client, name="FilterCo", email="admin@ft.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@ft.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = (await client.get("/api/v1/users/me", headers=admin_headers)).json()["id"]

    u1_id = await _create_member(client, admin_headers, "u1@ft.com", "Valid1!Pass", "U1", "employee", ["docvault", "notifications"])
    u2_id = await _create_member(client, admin_headers, "u2@ft.com", "Valid1!Pass", "U2", "employee", ["docvault", "notifications"])
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@ft.com', 'Valid1!Pass')}"}

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


@pytest.mark.asyncio
async def test_list_approvers_success_and_self_exclusion(client: AsyncClient):
    await create_test_company(client, name="ApproverListCo", email="admin@applist.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@applist.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = (await client.get("/api/v1/users/me", headers=admin_headers)).json()["id"]

    e1_id = await _create_member(client, admin_headers, "e1@applist.com", "Valid1!Pass", "Employee One", "employee", ["docvault", "notifications"])
    e2_id = await _create_member(client, admin_headers, "e2@applist.com", "Valid1!Pass", "Employee Two", "employee", ["docvault", "notifications"])
    # Employee without docvault module
    nodoc_id = await _create_member(client, admin_headers, "nodoc@applist.com", "Valid1!Pass", "No Doc User", "employee", ["assets"])

    # E1 calls /api/v1/docvault/approvers
    e1_token = await get_company_token(client, email="e1@applist.com", password="Valid1!Pass")
    e1_headers = {"Authorization": f"Bearer {e1_token}"}

    resp = await client.get("/api/v1/docvault/approvers", headers=e1_headers)
    assert resp.status_code == 200, resp.text
    approvers = resp.json()
    approver_ids = {a["id"] for a in approvers}

    # E1 can see Admin and E2
    assert admin_id in approver_ids
    assert e2_id in approver_ids

    # E1 CANNOT see self (self-exclusion)
    assert e1_id not in approver_ids

    # User without docvault module is excluded
    assert nodoc_id not in approver_ids


@pytest.mark.asyncio
async def test_list_approvers_filters_inactive_and_restricted_bucket(client: AsyncClient):
    await create_test_company(client, name="BucketAppCo", email="admin@bapp.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@bapp.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = (await client.get("/api/v1/users/me", headers=admin_headers)).json()["id"]

    u1_id = await _create_member(client, admin_headers, "u1@bapp.com", "Valid1!Pass", "User One", "employee", ["docvault", "notifications"])
    u2_id = await _create_member(client, admin_headers, "u2@bapp.com", "Valid1!Pass", "User Two", "employee", ["docvault", "notifications"])
    deact_id = await _create_member(client, admin_headers, "deact@bapp.com", "Valid1!Pass", "Deact User", "employee", ["docvault", "notifications"])

    # Deactivate deact_id
    await client.patch(f"/api/v1/users/{deact_id}/deactivate", headers=admin_headers)

    # Create restricted bucket with access only to u1
    b_resp = await client.post("/api/v1/docvault/buckets", json={"name": "Confidential Finance"}, headers=admin_headers)
    bucket_id = b_resp.json()["id"]
    await client.patch(
        f"/api/v1/docvault/buckets/{bucket_id}/access",
        json={"visibility": "restricted", "user_ids": [u1_id]},
        headers=admin_headers,
    )

    # General approvers list excludes deactivated user
    resp = await client.get("/api/v1/docvault/approvers", headers=admin_headers)
    assert resp.status_code == 200
    all_ids = {a["id"] for a in resp.json()}
    assert deact_id not in all_ids
    assert u1_id in all_ids
    assert u2_id in all_ids

    # Querying with restricted bucket_id only returns Admin and u1
    u1_headers = {"Authorization": f"Bearer {await get_company_token(client, 'u1@bapp.com', 'Valid1!Pass')}"}
    resp = await client.get(f"/api/v1/docvault/approvers?bucket_id={bucket_id}", headers=u1_headers)
    assert resp.status_code == 200
    bucket_approvers = resp.json()
    b_ids = {a["id"] for a in bucket_approvers}
    assert admin_id in b_ids
    assert u2_id not in b_ids  # u2 does not have access to this restricted bucket
    assert u1_id not in b_ids  # u1 is caller so excluded by self-exclusion


@pytest.mark.asyncio
async def test_list_approvers_success_for_employee_caller(client: AsyncClient):
    await create_test_company(client, name="EmployeeCallCo", email="admin@empcall.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@empcall.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = (await client.get("/api/v1/users/me", headers=admin_headers)).json()["id"]

    # Employee with docvault module
    doc_id = await _create_member(client, admin_headers, "docmember@empcall.com", "Valid1!Pass", "Doc Member", "employee", ["docvault", "notifications"])
    doc_token = await get_company_token(client, email="docmember@empcall.com", password="Valid1!Pass")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    # Employee without docvault module
    nodoc_id = await _create_member(client, admin_headers, "nodoc@empcall.com", "Valid1!Pass", "No Doc", "employee", ["assets"])

    resp = await client.get("/api/v1/docvault/approvers", headers=doc_headers)
    assert resp.status_code == 200
    approver_ids = {a["id"] for a in resp.json()}
    assert admin_id in approver_ids
    assert doc_id not in approver_ids  # self excluded
    assert nodoc_id not in approver_ids  # nodoc excluded


@pytest.mark.asyncio
async def test_pending_approval_creator_and_peer_cannot_modify_or_delete(client: AsyncClient):
    await create_test_company(client, name="ImmutCo", email="admin@immut.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@immut.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_id = (await client.get("/api/v1/users/me", headers=admin_headers)).json()["id"]

    # Creator (Alice) and Peer (Charlie) and Approver (Bob)
    alice_id = await _create_member(client, admin_headers, "alice@immut.com", "Valid1!Pass", "Alice Creator", "employee", ["docvault", "notifications"])
    bob_id = await _create_member(client, admin_headers, "bob@immut.com", "Valid1!Pass", "Bob Approver", "employee", ["docvault", "notifications"])
    charlie_id = await _create_member(client, admin_headers, "charlie@immut.com", "Valid1!Pass", "Charlie Peer", "employee", ["docvault", "notifications"])

    alice_headers = {"Authorization": f"Bearer {await get_company_token(client, 'alice@immut.com', 'Valid1!Pass')}"}
    bob_headers = {"Authorization": f"Bearer {await get_company_token(client, 'bob@immut.com', 'Valid1!Pass')}"}
    charlie_headers = {"Authorization": f"Bearer {await get_company_token(client, 'charlie@immut.com', 'Valid1!Pass')}"}

    # Alice uploads document with approval requested by Bob
    files = {"file": ("budget_proposal.pdf", b"budget data", "application/pdf")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Budget 2026", "needs_approval": "true", "approver_id": bob_id},
        files=files,
        headers=alice_headers,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    assert resp.json()["status"] == "pending_approval"

    # 1. Alice (creator) attempts to PATCH title -> 403
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"title": "Hacked Title"}, headers=alice_headers)
    assert resp.status_code == 403, resp.text

    # 2. Alice attempts to PATCH tags -> 403
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"tags": ["hacked"]}, headers=alice_headers)
    assert resp.status_code == 403

    # 3. Alice attempts to PATCH is_editable -> 403
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"is_editable": False}, headers=alice_headers)
    assert resp.status_code == 403

    # 4. Alice attempts to PATCH approver_id -> 403
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"approver_id": charlie_id}, headers=alice_headers)
    assert resp.status_code == 403

    # 5. Alice attempts to upload new version -> 403
    v_files = {"file": ("budget_v2.pdf", b"v2", "application/pdf")}
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/versions", files=v_files, headers=alice_headers)
    assert resp.status_code == 403

    # 6. Alice attempts to DELETE / archive -> 403
    resp = await client.delete(f"/api/v1/docvault/documents/{doc_id}", headers=alice_headers)
    assert resp.status_code == 403

    # 7. Charlie (peer employee) attempts to PATCH and DELETE -> 403
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"title": "Charlie Title"}, headers=charlie_headers)
    assert resp.status_code == 403
    resp = await client.delete(f"/api/v1/docvault/documents/{doc_id}", headers=charlie_headers)
    assert resp.status_code == 403

    # 8. Bob (approver) can review and approve -> 200
    resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "verified", "approval_notes": "Looks solid, approved."},
        headers=bob_headers,
    )
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["status"] == "verified"
    assert doc["approval_notes"] == "Looks solid, approved."
    assert doc["approved_at"] is not None


def test_document_update_schema_excludes_approval_fields():
    from app.schemas.docvault import DocumentUpdate
    
    assert "status" not in DocumentUpdate.model_fields
    assert "approval_notes" not in DocumentUpdate.model_fields


def test_document_review_request_schema():
    from app.schemas.docvault import DocumentReviewRequest
    from pydantic import ValidationError

    # Valid initialization
    req = DocumentReviewRequest(decision="verified", approval_notes="Looks good")
    assert req.decision == "verified"
    assert req.approval_notes == "Looks good"

    # Invalid decision
    with pytest.raises(ValidationError):
        DocumentReviewRequest(decision="invalid_status")


@pytest.mark.asyncio
async def test_review_requires_pending_state(client: AsyncClient):
    await create_test_company(client, name="ReviewCo1", email="admin@reviewco1.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@reviewco1.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@reviewco1.com", "Valid1!Pass", "Uploader", "employee", ["docvault", "notifications"])
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@reviewco1.com', 'Valid1!Pass')}"}

    # Upload doc without approval
    files = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Doc"}, files=files, headers=h1)
    doc_id = resp.json()["id"]

    # Try to review
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/review", json={"decision": "verified"}, headers=admin_headers)
    assert resp.status_code == 409
    assert "pending approval" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_review_rejects_non_approver(client: AsyncClient):
    await create_test_company(client, name="ReviewCo2", email="admin@reviewco2.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@reviewco2.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@reviewco2.com", "Valid1!Pass", "Uploader", "employee", ["docvault", "notifications"])
    u2_id = await _create_member(client, admin_headers, "u2@reviewco2.com", "Valid1!Pass", "Approver", "employee", ["docvault", "notifications"])
    u3_id = await _create_member(client, admin_headers, "u3@reviewco2.com", "Valid1!Pass", "Other", "employee", ["docvault", "notifications"])
    
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@reviewco2.com', 'Valid1!Pass')}"}
    h3 = {"Authorization": f"Bearer {await get_company_token(client, 'u3@reviewco2.com', 'Valid1!Pass')}"}

    files = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Doc", "needs_approval": "true", "approver_id": u2_id}, files=files, headers=h1)
    doc_id = resp.json()["id"]

    # u3 tries to review
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/review", json={"decision": "verified"}, headers=h3)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_uploader_cannot_approve_own_document(client: AsyncClient):
    await create_test_company(client, name="ReviewCo3", email="admin@reviewco3.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@reviewco3.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@reviewco3.com", "Valid1!Pass", "Uploader", "employee", ["docvault", "notifications"])
    u2_id = await _create_member(client, admin_headers, "u2@reviewco3.com", "Valid1!Pass", "Approver", "employee", ["docvault", "notifications"])
    
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@reviewco3.com', 'Valid1!Pass')}"}

    files = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Doc", "needs_approval": "true", "approver_id": u2_id}, files=files, headers=h1)
    doc_id = resp.json()["id"]

    # u1 (uploader) tries to review
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/review", json={"decision": "verified"}, headers=h1)
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_unrelated_user_cannot_edit_document_metadata(client: AsyncClient):
    await create_test_company(client, name="EditCo1", email="admin@editco1.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@editco1.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@editco1.com", "Valid1!Pass", "Creator", "employee", ["docvault"])
    u2_id = await _create_member(client, admin_headers, "u2@editco1.com", "Valid1!Pass", "Other", "employee", ["docvault"])
    
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@editco1.com', 'Valid1!Pass')}"}
    h2 = {"Authorization": f"Bearer {await get_company_token(client, 'u2@editco1.com', 'Valid1!Pass')}"}

    # u1 uploads document
    files = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Doc"}, files=files, headers=h1)
    doc_id = resp.json()["id"]

    # u2 tries to edit title
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"title": "Hacked"}, headers=h2)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_only_admin_can_unlock(client: AsyncClient):
    await create_test_company(client, name="EditCo2", email="admin@editco2.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@editco2.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@editco2.com", "Valid1!Pass", "Creator", "employee", ["docvault"])
    u2_id = await _create_member(client, admin_headers, "u2@editco2.com", "Valid1!Pass", "Other", "employee", ["docvault"])
    
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@editco2.com', 'Valid1!Pass')}"}
    h2 = {"Authorization": f"Bearer {await get_company_token(client, 'u2@editco2.com', 'Valid1!Pass')}"}

    # u1 uploads document, locked
    files = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Doc", "is_editable": "false"}, files=files, headers=h1)
    doc_id = resp.json()["id"]

    # u2 (not admin) tries to unlock -> 403
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"is_editable": True}, headers=h2)
    assert resp.status_code == 403

    # u1 (creator employee, not admin) tries to unlock -> 403 Forbidden
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"is_editable": True}, headers=h1)
    assert resp.status_code == 403
    assert "Only administrators can unlock a finalized document" in resp.json()["detail"]

    # Admin tries to unlock -> allowed
    admin_resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"is_editable": True}, headers=admin_headers)
    assert admin_resp.status_code == 200
    assert admin_resp.json()["is_editable"] is True


@pytest.mark.asyncio
async def test_employee_cannot_self_verify_via_patch(client: AsyncClient):
    await create_test_company(client, name="EditCo3", email="admin@editco3.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@editco3.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@editco3.com", "Valid1!Pass", "Creator", "employee", ["docvault"])
    u2_id = await _create_member(client, admin_headers, "u2@editco3.com", "Valid1!Pass", "Approver", "employee", ["docvault"])
    
    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@editco3.com', 'Valid1!Pass')}"}

    # u1 uploads document with approval request
    files = {"file": ("doc.txt", b"content", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Doc", "needs_approval": "true", "approver_id": u2_id}, files=files, headers=h1)
    doc_id = resp.json()["id"]

    # u1 tries to patch status -> extra="forbid" returns 422 Unprocessable Entity
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"status": "verified"}, headers=h1)
    assert resp.status_code == 422

    # u1 tries to patch approval_notes -> returns 422
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"approval_notes": "Bypassed"}, headers=h1)
    assert resp.status_code == 422

    # u1 tries to patch approved_by -> returns 422
    resp = await client.patch(f"/api/v1/docvault/documents/{doc_id}", json={"approved_by": str(u1_id)}, headers=h1)
    assert resp.status_code == 422
    
    resp2 = await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=h1)
    assert resp2.json()["status"] == "pending_approval"


@pytest.mark.asyncio
async def test_review_decision_action_required_does_not_set_approved_by(client: AsyncClient):
    await create_test_company(client, name="ActionCo", email="admin@actionco.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@actionco.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    creator_id = await _create_member(client, admin_headers, "c@actionco.com", "Valid1!Pass", "Creator", "employee", ["docvault"])
    approver_id = await _create_member(client, admin_headers, "a@actionco.com", "Valid1!Pass", "Approver Alice", "employee", ["docvault"])

    c_headers = {"Authorization": f"Bearer {await get_company_token(client, 'c@actionco.com', 'Valid1!Pass')}"}
    a_headers = {"Authorization": f"Bearer {await get_company_token(client, 'a@actionco.com', 'Valid1!Pass')}"}

    files = {"file": ("contract.pdf", b"pdf content", "application/pdf")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Contract", "needs_approval": "true", "approver_id": approver_id},
        files=files,
        headers=c_headers,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    # Approver requests changes
    rev_resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "action_required", "approval_notes": "Missing appendix B"},
        headers=a_headers,
    )
    assert rev_resp.status_code == 200
    data = rev_resp.json()
    assert data["status"] == "action_required"
    assert data["approval_notes"] == "Missing appendix B"
    assert data["approved_by"] is None
    assert data["approved_by_name"] is None
    assert data["approved_at"] is None


@pytest.mark.asyncio
async def test_review_decision_verified_sets_approved_by_and_response_fields(client: AsyncClient):
    await create_test_company(client, name="VerifyCo", email="admin@verifyco.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@verifyco.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    creator_id = await _create_member(client, admin_headers, "c@verifyco.com", "Valid1!Pass", "Creator Chris", "employee", ["docvault"])
    approver_id = await _create_member(client, admin_headers, "a@verifyco.com", "Valid1!Pass", "Approver Alice", "employee", ["docvault"])

    c_headers = {"Authorization": f"Bearer {await get_company_token(client, 'c@verifyco.com', 'Valid1!Pass')}"}
    a_headers = {"Authorization": f"Bearer {await get_company_token(client, 'a@verifyco.com', 'Valid1!Pass')}"}

    files = {"file": ("report.pdf", b"pdf content", "application/pdf")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Report", "needs_approval": "true", "approver_id": approver_id},
        files=files,
        headers=c_headers,
    )
    doc_id = resp.json()["id"]

    rev_resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "verified", "approval_notes": "All calculations checked"},
        headers=a_headers,
    )
    assert rev_resp.status_code == 200
    data = rev_resp.json()
    assert data["status"] == "verified"
    assert data["approved_by"] == approver_id
    assert data["approved_by_name"] == "Approver Alice"
    assert data["approved_at"] is not None
    assert data["approval_notes"] == "All calculations checked"


@pytest.mark.asyncio
async def test_self_approval_assignment_on_upload_rejected(client: AsyncClient):
    await create_test_company(client, name="SelfAppCo", email="admin@selfapp.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@selfapp.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    emp_id = await _create_member(client, admin_headers, "emp@selfapp.com", "Valid1!Pass", "Employee", "employee", ["docvault"])
    emp_headers = {"Authorization": f"Bearer {await get_company_token(client, 'emp@selfapp.com', 'Valid1!Pass')}"}

    files = {"file": ("self.txt", b"secret", "text/plain")}
    # Non-admin employee attempts to set approver_id to themselves
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "SelfDoc", "needs_approval": "true", "approver_id": emp_id},
        files=files,
        headers=emp_headers,
    )
    assert resp.status_code == 400
    assert "Cannot assign yourself as approver" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_request_approval_lifecycle(client: AsyncClient):
    await create_test_company(client, name="ReqAppCo", email="admin@reqapp.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@reqapp.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    creator_id = await _create_member(client, admin_headers, "creator@reqapp.com", "Valid1!Pass", "Creator Bob", "employee", ["docvault"])
    approver_id = await _create_member(client, admin_headers, "approver@reqapp.com", "Valid1!Pass", "Approver Ann", "employee", ["docvault"])

    c_headers = {"Authorization": f"Bearer {await get_company_token(client, 'creator@reqapp.com', 'Valid1!Pass')}"}
    a_headers = {"Authorization": f"Bearer {await get_company_token(client, 'approver@reqapp.com', 'Valid1!Pass')}"}

    # Upload document without approval initially (status == uploaded)
    files = {"file": ("draft.txt", b"draft v1", "text/plain")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Draft Policy", "needs_approval": "false"},
        files=files,
        headers=c_headers,
    )
    assert resp.status_code == 201
    doc_id = resp.json()["id"]
    assert resp.json()["status"] == "uploaded"

    # Creator requests approval
    req_resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/request-approval",
        json={"approver_id": approver_id},
        headers=c_headers,
    )
    assert req_resp.status_code == 200
    assert req_resp.json()["status"] == "pending_approval"
    assert req_resp.json()["approver_id"] == approver_id

    # Approver requests changes
    rev_resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "action_required", "approval_notes": "Please revise section 3"},
        headers=a_headers,
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["status"] == "action_required"

    # Creator re-submits for approval
    resub_resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/request-approval",
        json={"approver_id": approver_id},
        headers=c_headers,
    )
    assert resub_resp.status_code == 200
    assert resub_resp.json()["status"] == "pending_approval"

    # Approver approves
    final_resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "verified", "approval_notes": "Looks good!"},
        headers=a_headers,
    )
    assert final_resp.status_code == 200
    assert final_resp.json()["status"] == "verified"
    assert final_resp.json()["approved_by"] == approver_id


@pytest.mark.asyncio
async def test_cannot_request_approval_with_self_or_invalid_status(client: AsyncClient):
    await create_test_company(client, name="ReqAppCo2", email="admin@reqapp2.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@reqapp2.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    creator_id = await _create_member(client, admin_headers, "c@reqapp2.com", "Valid1!Pass", "Creator", "employee", ["docvault"])
    other_id = await _create_member(client, admin_headers, "o@reqapp2.com", "Valid1!Pass", "Other", "employee", ["docvault"])

    c_headers = {"Authorization": f"Bearer {await get_company_token(client, 'c@reqapp2.com', 'Valid1!Pass')}"}
    o_headers = {"Authorization": f"Bearer {await get_company_token(client, 'o@reqapp2.com', 'Valid1!Pass')}"}

    files = {"file": ("file.txt", b"content", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Test", "needs_approval": "false"}, files=files, headers=c_headers)
    doc_id = resp.json()["id"]

    # Creator cannot assign self
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/request-approval", json={"approver_id": creator_id}, headers=c_headers)
    assert resp.status_code == 400
    assert "Cannot assign yourself as approver" in resp.json()["detail"]

    # Unrelated user cannot request approval
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/request-approval", json={"approver_id": creator_id}, headers=o_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unrelated_user_cannot_upload_version_or_delete_document(client: AsyncClient):
    await create_test_company(client, name="VersionCo", email="admin@versionco.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@versionco.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@versionco.com", "Valid1!Pass", "Uploader", "employee", ["docvault"])
    u2_id = await _create_member(client, admin_headers, "u2@versionco.com", "Valid1!Pass", "Peer", "employee", ["docvault"])

    h1 = {"Authorization": f"Bearer {await get_company_token(client, 'u1@versionco.com', 'Valid1!Pass')}"}
    h2 = {"Authorization": f"Bearer {await get_company_token(client, 'u2@versionco.com', 'Valid1!Pass')}"}

    # u1 uploads document
    files = {"file": ("v1.txt", b"v1 content", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Shared Doc"}, files=files, headers=h1)
    assert resp.status_code == 201
    doc_id = resp.json()["id"]

    # Peer u2 tries to upload version to u1's document -> 403 Forbidden
    v_files = {"file": ("v2.txt", b"hacked v2", "text/plain")}
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/versions", files=v_files, headers=h2)
    assert resp.status_code == 403
    assert "Only creator or admin can upload new versions" in resp.json()["detail"]

    # Peer u2 tries to delete u1's document -> 403 Forbidden
    resp = await client.delete(f"/api/v1/docvault/documents/{doc_id}", headers=h2)
    assert resp.status_code == 403
    assert "Only creator or admin can archive a document" in resp.json()["detail"]

    # u1 (creator) can upload new version
    resp = await client.post(f"/api/v1/docvault/documents/{doc_id}/versions", files={"file": ("v2.txt", b"valid v2", "text/plain")}, headers=h1)
    assert resp.status_code == 200

    # u1 (creator) can archive document
    resp = await client.delete(f"/api/v1/docvault/documents/{doc_id}", headers=h1)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_version_upload_on_verified_document_resets_verification(client: AsyncClient):
    await create_test_company(client, name="ResetCo", email="admin@resetco.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@resetco.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    creator_id = await _create_member(client, admin_headers, "c@resetco.com", "Valid1!Pass", "Creator", "employee", ["docvault"])
    approver_id = await _create_member(client, admin_headers, "a@resetco.com", "Valid1!Pass", "Approver", "employee", ["docvault"])

    c_headers = {"Authorization": f"Bearer {await get_company_token(client, 'c@resetco.com', 'Valid1!Pass')}"}
    a_headers = {"Authorization": f"Bearer {await get_company_token(client, 'a@resetco.com', 'Valid1!Pass')}"}

    files = {"file": ("v1.txt", b"original audited content", "text/plain")}
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Audited Policy", "needs_approval": "true", "approver_id": approver_id},
        files=files,
        headers=c_headers,
    )
    doc_id = resp.json()["id"]

    # Approver verifies the document
    await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "verified"},
        headers=a_headers,
    )
    doc_state = (await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=c_headers)).json()
    assert doc_state["status"] == "verified"
    assert doc_state["approved_by"] == approver_id

    # Creator uploads a new file version -> status must reset to uploaded so unreviewed files are not verified
    resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/versions",
        files={"file": ("v2.txt", b"modified content", "text/plain")},
        headers=c_headers,
    )
    assert resp.status_code == 200
    new_doc_state = (await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=c_headers)).json()
    assert new_doc_state["status"] == "uploaded"
    assert new_doc_state["approved_by"] is None
    assert new_doc_state["approved_at"] is None


@pytest.mark.asyncio
async def test_cannot_review_non_pending_document(client: AsyncClient):
    await create_test_company(client, name="ConflictCo", email="admin@conflict.com", password="Valid1!Pass")
    admin_token = await get_company_token(client, email="admin@conflict.com", password="Valid1!Pass")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    u1_id = await _create_member(client, admin_headers, "u1@conflict.com", "Valid1!Pass", "Creator", "employee", ["docvault"])
    files = {"file": ("plain.txt", b"data", "text/plain")}
    resp = await client.post("/api/v1/docvault/documents", data={"title": "Plain"}, files=files, headers=admin_headers)
    doc_id = resp.json()["id"]

    # Document is in status "uploaded", not "pending_approval" -> 409 Conflict
    rev_resp = await client.post(
        f"/api/v1/docvault/documents/{doc_id}/review",
        json={"decision": "verified"},
        headers=admin_headers,
    )
    assert rev_resp.status_code == 409
    assert "Document is not pending approval" in rev_resp.json()["detail"]


@pytest.mark.asyncio
async def test_admin_can_restore_archived_document(client: AsyncClient):
    email = "admin_restore@testco.com"
    await create_test_company(client, name="Restore Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Upload document
    files = {"file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")}
    upload_res = await client.post("/api/v1/docvault/documents", files=files, data={"title": "Doc to Archive"}, headers=admin_headers)
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # Archive document via DELETE
    del_res = await client.delete(f"/api/v1/docvault/documents/{doc_id}", headers=admin_headers)
    assert del_res.status_code == 204

    # Verify status is archived
    get_res = await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=admin_headers)
    assert get_res.json()["status"] == "archived"
    assert get_res.json()["is_editable"] is False

    # Admin calls restore
    restore_res = await client.post(f"/api/v1/docvault/documents/{doc_id}/restore", headers=admin_headers)
    assert restore_res.status_code == 200
    data = restore_res.json()
    assert data["status"] == "uploaded"
    assert data["is_editable"] is True
    assert data["approved_by"] is None
    assert data["approved_at"] is None

    # Verify activity log
    log_res = await client.get("/api/v1/activity-log", params={"entity_type": "document", "entity_id": doc_id}, headers=admin_headers)
    assert log_res.status_code == 200
    logs = log_res.json()
    restore_log = next((l for l in logs if l["action"] == "document.restored"), None)
    assert restore_log is not None


@pytest.mark.asyncio
async def test_employee_cannot_restore_archived_document(client: AsyncClient):
    email = "admin_emp_restore@testco.com"
    emp_email = "emp_restore@testco.com"
    await create_test_company(client, name="Emp Restore Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_emp_res = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": emp_email,
            "password": "Valid1!Pass",
            "full_name": "Doc Employee",
            "role": "employee",
            "accessible_modules": ["docvault"],
        },
    )
    assert create_emp_res.status_code == 201
    emp_token = await get_company_token(client, email=emp_email, password="Valid1!Pass")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Employee uploads document
    files = {"file": ("emp.pdf", b"%PDF-1.4 employee doc", "application/pdf")}
    upload_res = await client.post("/api/v1/docvault/documents", files=files, data={"title": "Emp Doc"}, headers=emp_headers)
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["id"]

    # Archive document
    await client.delete(f"/api/v1/docvault/documents/{doc_id}", headers=emp_headers)

    # Employee attempts restore -> 403
    restore_res = await client.post(f"/api/v1/docvault/documents/{doc_id}/restore", headers=emp_headers)
    assert restore_res.status_code == 403


@pytest.mark.asyncio
async def test_restore_non_archived_document_returns_409(client: AsyncClient):
    email = "admin_non_archived@testco.com"
    await create_test_company(client, name="Non Archived Co", email=email)
    admin_token = await get_company_token(client, email=email)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    files = {"file": ("test.pdf", b"%PDF-1.4 active doc", "application/pdf")}
    upload_res = await client.post("/api/v1/docvault/documents", files=files, data={"title": "Active Doc"}, headers=admin_headers)
    doc_id = upload_res.json()["id"]

    # Call restore on active doc -> 409 Conflict
    restore_res = await client.post(f"/api/v1/docvault/documents/{doc_id}/restore", headers=admin_headers)
    assert restore_res.status_code == 409


@pytest.mark.asyncio
async def test_patch_document_rejects_a_status_field_even_for_an_admin(client: AsyncClient):
    """The server half of the anti-test.

    KUB-007 removed `status` from DocumentUpdate because setting it directly was
    the self-approval bypass: an uploader could mark their own document verified
    without review. `extra="forbid"` makes the attempt a 422 rather than a
    silently-ignored field. Asserted for an admin too, so nobody "fixes" this by
    re-adding the field behind a role check.
    """
    await create_test_company(
        client, name="StatusCo", email="admin@statusco.com", password="Valid1!Pass"
    )
    token = await get_company_token(
        client, email="admin@statusco.com", password="Valid1!Pass"
    )
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("policy.pdf", b"pdf content", "application/pdf")}
    upload = await client.post(
        "/api/v1/docvault/documents",
        files=files,
        data={"title": "Policy"},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["id"]
    assert upload.json()["status"] == "uploaded"

    for body in ({"status": "verified"}, {"status": "verified", "title": "Renamed"}):
        res = await client.patch(
            f"/api/v1/docvault/documents/{doc_id}", json=body, headers=headers
        )
        assert res.status_code == 422, f"{body} -> {res.status_code} {res.text}"

    # Neither the status nor the co-submitted title may have been applied.
    after = await client.get(f"/api/v1/docvault/documents/{doc_id}", headers=headers)
    assert after.json()["status"] == "uploaded"
    assert after.json()["title"] == "Policy"


@pytest.mark.asyncio
async def test_document_update_schema_has_no_status_field():
    """Fails the moment someone re-adds the field, without needing a request."""
    from app.schemas.docvault import DocumentUpdate

    assert "status" not in DocumentUpdate.model_fields
    assert DocumentUpdate.model_config.get("extra") == "forbid"


