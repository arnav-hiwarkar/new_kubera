import uuid
from httpx import AsyncClient
import pytest
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditease import RequirementResponse, RequirementResponseDocument
from app.models.docvault import Document, DocumentAccessOverride, Bucket, BucketVisibility
from tests.conftest import (
    create_test_company,
    get_company_token,
    create_test_auditor,
    get_auditor_token,
)


async def _make_engagement(client: AsyncClient, headers: dict, label: str = "FY24") -> str:
    resp = await client.post("/api/v1/auditease/engagements", json={"period_label": label}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_multi_file_uploads_in_one_round(client: AsyncClient, db: AsyncSession):
    await create_test_company(client, email="mfiles@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='mfiles@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="mfiles@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='mfiles@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "mfiles@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    # Create requirement
    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Upload 6 files"},
        headers=aud_headers,
    )
    assert resp.status_code == 200
    req_id = resp.json()["id"]

    # Upload 6 files in one round
    files = [("files", (f"statement_{i}.pdf", b"pdfcontent123", "application/pdf")) for i in range(6)]
    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "All 6 statements attached"},
        files=files,
        headers=co_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["submission_count"] == 1
    assert data["document_count"] == 6
    assert len(data["submissions"]) == 1

    submission = data["submissions"][0]
    assert submission["round_number"] == 1
    assert submission["text_answer"] == "All 6 statements attached"
    assert len(submission["documents"]) == 6
    for i, doc in enumerate(submission["documents"]):
        assert doc["filename"] == f"statement_{i}.pdf"
        assert doc["size_bytes"] == len(b"pdfcontent123")
        assert doc["mime_type"] == "application/pdf"
        assert doc["document_id"] is not None


@pytest.mark.asyncio
async def test_mixed_submission_types_and_empty_validation(client: AsyncClient):
    await create_test_company(client, email="mixed@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='mixed@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="mixed@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='mixed@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "mixed@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Test mixed submissions"},
        headers=aud_headers,
    )
    req_id = resp.json()["id"]

    # Pre-upload a document into DocVault
    dv_resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Existing Doc"},
        files={"file": ("vault_doc.pdf", b"vaultbytes", "application/pdf")},
        headers=co_headers,
    )
    assert dv_resp.status_code == 201
    vault_doc_id = dv_resp.json()["id"]

    # 1. Text-only submission (round 1)
    r1 = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Text only answer"},
        headers=co_headers,
    )
    assert r1.status_code == 200
    assert r1.json()["submission_count"] == 1
    assert r1.json()["document_count"] == 0

    # 2. Files-only submission (round 2)
    r2 = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        files=[("files", ("file_round2.txt", b"hello", "text/plain"))],
        headers=co_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["submission_count"] == 2
    assert r2.json()["document_count"] == 1

    # 3. Picked-documents-only submission (round 3)
    r3 = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"document_ids": [vault_doc_id]},
        headers=co_headers,
    )
    assert r3.status_code == 200
    assert r3.json()["submission_count"] == 3
    assert r3.json()["document_count"] == 2

    # 4. Mixed text + uploaded files + picked documents (round 4)
    r4 = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Mixed round", "document_ids": [vault_doc_id]},
        files=[("files", ("extra.txt", b"extra content", "text/plain"))],
        headers=co_headers,
    )
    assert r4.status_code == 200
    assert r4.json()["submission_count"] == 4
    assert r4.json()["document_count"] == 4

    # 5. Empty submission -> 422
    empty_resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={},
        headers=co_headers,
    )
    assert empty_resp.status_code == 422


@pytest.mark.asyncio
async def test_round_number_increment(client: AsyncClient):
    await create_test_company(client, email="rounds@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='rounds@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="rounds@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='rounds@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "rounds@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Multi-round test"},
        headers=aud_headers,
    )
    req_id = resp.json()["id"]

    for i in range(1, 4):
        resp = await client.post(
            f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
            data={"text_answer": f"Submission round {i}"},
            headers=co_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["submission_count"] == i

    req_data = (await client.get(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests", headers=co_headers)).json()[0]
    rounds = [s["round_number"] for s in req_data["submissions"]]
    assert rounds == [3, 2, 1]


@pytest.mark.asyncio
async def test_auditor_access_overrides_and_download(client: AsyncClient, db: AsyncSession):
    await create_test_company(client, email="overrides@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='overrides@co.com', password='pass1234')}"}
    
    # Auditor 1 with requirements + documents area
    await create_test_auditor(client, email="aud_req@aud.com", password="pass1234")
    aud1_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='aud_req@aud.com', password='pass1234')}"}

    # Auditor 2 with only queries area
    await create_test_auditor(client, email="aud_queries@aud.com", password="pass1234")
    aud2_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='aud_queries@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers)

    # Invite Auditor 1 (default has requirements area)
    inv1 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "aud_req@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud1_headers)

    # Invite Auditor 2 and restrict to queries only
    inv2 = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "aud_queries@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud2_headers)
    aud2_id = next(a["auditor_id"] for a in inv2.json()["auditors"] if a["email"] == "aud_queries@aud.com")
    patch_resp = await client.patch(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/{aud2_id}",
        json={"area_permissions": {"trial_balance": False, "entries": False, "requirements": False, "queries": True, "documents": False}},
        headers=co_headers,
    )
    assert patch_resp.status_code == 200

    # Create requirement and respond with uploaded file
    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Access test req"},
        headers=aud1_headers,
    )
    req_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        files=[("files", ("secret_statement.pdf", b"secret auditor data", "application/pdf"))],
        headers=co_headers,
    )
    assert resp.status_code == 200
    doc_id = resp.json()["submissions"][0]["documents"][0]["document_id"]

    # Auditor 1 can access document
    doc_resp = await client.get(f"/api/v1/auditor/documents/{doc_id}", headers=aud1_headers)
    assert doc_resp.status_code == 200

    # Auditor 2 (no requirements/documents area) cannot access document
    doc2_resp = await client.get(f"/api/v1/auditor/documents/{doc_id}", headers=aud2_headers)
    assert doc2_resp.status_code == 404


@pytest.mark.asyncio
async def test_document_title_convention_and_tags(client: AsyncClient, db: AsyncSession):
    await create_test_company(client, email="tags@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='tags@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="tags@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='tags@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "tags@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    # Create 3 requirements so 3rd is REQ-003
    for i in range(2):
        await client.post(
            f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
            json={"description": f"Req {i+1}"},
            headers=aud_headers,
        )
    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Req 3"},
        headers=aud_headers,
    )
    req3 = resp.json()
    assert req3["requirement_id_str"] == "REQ-003"
    req3_id = req3["id"]

    # Submit file on REQ-003 round 1
    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req3_id}/respond",
        files=[("files", ("bank-statement-jan.pdf", b"content", "application/pdf"))],
        headers=co_headers,
    )
    assert resp.status_code == 200
    doc_id = uuid.UUID(resp.json()["submissions"][0]["documents"][0]["document_id"])

    # Query Document from database
    res = await db.execute(select(Document).where(Document.id == doc_id))
    doc = res.scalar_one()

    assert doc.title == "REQ-003 · Sub 1 · bank-statement-jan.pdf"
    assert doc.tags == ["audit-attachment", f"engagement:{eng_id}", "REQ-003"]
    assert doc.is_editable is False

    bucket_res = await db.execute(select(Bucket).where(Bucket.id == doc.bucket_id))
    bucket = bucket_res.scalar_one()
    assert bucket.name == "Audit - FY24"


@pytest.mark.asyncio
async def test_deleted_document_preserves_join_row(client: AsyncClient, db: AsyncSession):
    await create_test_company(client, email="del@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='del@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="del@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='del@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "del@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Delete document preservation test"},
        headers=aud_headers,
    )
    req_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        files=[("files", ("tax_invoice.pdf", b"invoice bytes", "application/pdf"))],
        headers=co_headers,
    )
    assert resp.status_code == 200
    doc_id_str = resp.json()["submissions"][0]["documents"][0]["document_id"]
    doc_id = uuid.UUID(doc_id_str)

    # Verify join row exists
    res = await db.execute(select(RequirementResponseDocument).where(RequirementResponseDocument.document_id == doc_id))
    join_row = res.scalar_one()
    assert join_row.filename == "tax_invoice.pdf"

    # Hard delete the document from database (simulates purge or permanent deletion)
    await db.execute(delete(Document).where(Document.id == doc_id))
    await db.commit()

    # Fetch requirement again — document_id is None, filename survives, document_count == 1
    req_resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", headers=aud_headers)
    req_data = req_resp.json()[0]
    assert req_data["document_count"] == 1
    assert len(req_data["submissions"][0]["documents"]) == 1
    sub_doc = req_data["submissions"][0]["documents"][0]
    assert sub_doc["document_id"] is None
    assert sub_doc["filename"] == "tax_invoice.pdf"


@pytest.mark.asyncio
async def test_cross_tenant_document_security_and_atomic_rollback(client: AsyncClient, db: AsyncSession):
    # Company A
    await create_test_company(client, email="tenanta@co.com", password="pass1234")
    co_a_headers = {"Authorization": f"Bearer {await get_company_token(client, email='tenanta@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="aud_a@aud.com", password="pass1234")
    aud_a_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='aud_a@aud.com', password='pass1234')}"}

    eng_a_id = await _make_engagement(client, co_a_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_a_id}/auditors/invite", json={"email": "aud_a@aud.com"}, headers=co_a_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_a_id}/accept", headers=aud_a_headers)

    resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_a_id}/requirement-requests",
        json={"description": "Tenant A Requirement"},
        headers=aud_a_headers,
    )
    req_a_id = resp.json()["id"]

    # Company B creates a doc in DocVault
    await create_test_company(client, email="tenantb@co.com", password="pass1234")
    co_b_headers = {"Authorization": f"Bearer {await get_company_token(client, email='tenantb@co.com', password='pass1234')}"}
    dv_b_resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Tenant B Secret Doc"},
        files={"file": ("secret_b.pdf", b"secret b bytes", "application/pdf")},
        headers=co_b_headers,
    )
    doc_b_id = dv_b_resp.json()["id"]

    # Company A also has a valid doc
    dv_a_resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Tenant A Doc"},
        files={"file": ("doc_a.pdf", b"doc a bytes", "application/pdf")},
        headers=co_a_headers,
    )
    doc_a_id = dv_a_resp.json()["id"]

    # 1. Tenant A attempts to pick Tenant B's doc -> 404
    bad_resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_a_id}/requirement-requests/{req_a_id}/respond",
        data={"document_ids": [doc_b_id]},
        headers=co_a_headers,
    )
    assert bad_resp.status_code == 404

    # Verify no response row was created
    res = await db.execute(select(RequirementResponse).where(RequirementResponse.requirement_id == uuid.UUID(req_a_id)))
    assert len(res.scalars().all()) == 0

    # 2. Tenant A attempts mixed valid + invalid (Tenant B's doc) -> 404 and NO response row created
    bad_mixed_resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_a_id}/requirement-requests/{req_a_id}/respond",
        data={"document_ids": [doc_a_id, doc_b_id]},
        headers=co_a_headers,
    )
    assert bad_mixed_resp.status_code == 404
    res = await db.execute(select(RequirementResponse).where(RequirementResponse.requirement_id == uuid.UUID(req_a_id)))
    assert len(res.scalars().all()) == 0

    # 3. Tenant B user attempts to respond to Tenant A's requirement -> 404
    b_on_a_resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_a_id}/requirement-requests/{req_a_id}/respond",
        data={"text_answer": "Malicious response"},
        headers=co_b_headers,
    )
    assert b_on_a_resp.status_code == 404

    # 4. Auditor without grant attempts to close requirement -> 403
    await create_test_auditor(client, email="uninvited_aud@aud.com", password="pass1234")
    uninvited_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='uninvited_aud@aud.com', password='pass1234')}"}
    unauth_resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_a_id}/requirement-requests/{req_a_id}/close",
        headers=uninvited_headers,
    )
    assert unauth_resp.status_code == 403


@pytest.mark.asyncio
async def test_company_member_role_file_upload_and_download(client: AsyncClient, db: AsyncSession):
    """Ensure non-admin company users (role='employee') can upload files to requirements and download them."""
    await create_test_company(client, email="admin_mem@co.com", password="pass1234")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='admin_mem@co.com', password='pass1234')}"}
    
    # Create employee user
    u_resp = await client.post(
        "/api/v1/users",
        json={"email": "employee@co.com", "password": "emppass123", "full_name": "Team Employee", "role": "employee", "accessible_modules": ["auditease", "docvault"]},
        headers=admin_headers,
    )
    assert u_resp.status_code == 201, u_resp.text
    emp_headers = {"Authorization": f"Bearer {await get_company_token(client, email='employee@co.com', password='emppass123')}"}

    await create_test_auditor(client, email="aud_mem@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='aud_mem@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, admin_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "aud_mem@aud.com"}, headers=admin_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    # Auditor creates requirement
    req_resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Employee upload test"},
        headers=aud_headers,
    )
    req_id = req_resp.json()["id"]

    # Employee responds with uploaded file
    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Employee response"},
        files=[("files", ("employee_statement.pdf", b"employee statement bytes", "application/pdf"))],
        headers=emp_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["submission_count"] == 1
    doc_id = data["submissions"][0]["documents"][0]["document_id"]
    assert doc_id is not None

    # Employee downloads document directly
    dl_resp = await client.get(f"/api/v1/docvault/documents/{doc_id}/download", headers=emp_headers)
    assert dl_resp.status_code == 200
    assert dl_resp.content == b"employee statement bytes"


@pytest.mark.asyncio
async def test_auditor_initiate_query_linked_to_requirement(client: AsyncClient, db: AsyncSession):
    """Ensure auditor can initiate a query linked to a specific requirement."""
    await create_test_company(client, email="query_req@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='query_req@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="aud_query_req@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='aud_query_req@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers)
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "aud_query_req@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    # 1. Auditor creates requirement REQ-001
    req_resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Please upload bank reconciliation"},
        headers=aud_headers,
    )
    req_id = req_resp.json()["id"]

    # 2. Auditor opens a query linked to this requirement
    q_resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/queries",
        data={"initial_message": "Clarification needed on bank statement date range", "requirement_id": req_id},
        headers=aud_headers,
    )
    assert q_resp.status_code == 200, q_resp.text
    query_data = q_resp.json()
    assert query_data["requirement_id"] == req_id
    assert query_data["status"] == "open"
    assert len(query_data["messages"]) == 1
    assert query_data["messages"][0]["text"] == "Clarification needed on bank statement date range"

    # 3. Fetch requirement to verify linked_query_count is enriched as 1
    req_list_resp = await client.get(f"/api/v1/auditor/engagements/{eng_id}/requirement-requests", headers=aud_headers)
    assert req_list_resp.status_code == 200
    req_data = req_list_resp.json()[0]
    assert req_data["linked_query_count"] == 1

    # 4. Also visible on company side
    co_req_list = await client.get(f"/api/v1/auditease/engagements/{eng_id}/requirement-requests", headers=co_headers)
    assert co_req_list.status_code == 200
    assert co_req_list.json()[0]["linked_query_count"] == 1


@pytest.mark.asyncio
async def test_per_engagement_dedicated_buckets(client: AsyncClient, db: AsyncSession):
    """Verify every engagement gets its own dedicated DocVault bucket named 'Audit - <period_label>'."""
    await create_test_company(client, email="multi_buckets@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='multi_buckets@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="aud_mb@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='aud_mb@aud.com', password='pass1234')}"}

    # Engagement 1: FY23-24
    eng1_id = await _make_engagement(client, co_headers, label="FY23-24")
    await client.post(f"/api/v1/auditease/engagements/{eng1_id}/auditors/invite", json={"email": "aud_mb@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng1_id}/accept", headers=aud_headers)

    # Engagement 2: FY24-25
    eng2_id = await _make_engagement(client, co_headers, label="FY24-25")
    await client.post(f"/api/v1/auditease/engagements/{eng2_id}/auditors/invite", json={"email": "aud_mb@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng2_id}/accept", headers=aud_headers)

    # Create requirement and upload file for Engagement 1
    req1 = (await client.post(f"/api/v1/auditor/engagements/{eng1_id}/requirement-requests", json={"description": "Req 1"}, headers=aud_headers)).json()
    resp1 = await client.post(
        f"/api/v1/auditease/engagements/{eng1_id}/requirement-requests/{req1['id']}/respond",
        files=[("files", ("eng1_doc.pdf", b"content1", "application/pdf"))],
        headers=co_headers,
    )
    assert resp1.status_code == 200
    doc1_id = uuid.UUID(resp1.json()["submissions"][0]["documents"][0]["document_id"])

    # Create requirement and upload file for Engagement 2
    req2 = (await client.post(f"/api/v1/auditor/engagements/{eng2_id}/requirement-requests", json={"description": "Req 2"}, headers=aud_headers)).json()
    resp2 = await client.post(
        f"/api/v1/auditease/engagements/{eng2_id}/requirement-requests/{req2['id']}/respond",
        files=[("files", ("eng2_doc.pdf", b"content2", "application/pdf"))],
        headers=co_headers,
    )
    assert resp2.status_code == 200
    doc2_id = uuid.UUID(resp2.json()["submissions"][0]["documents"][0]["document_id"])

    # Verify bucket 1 is "Audit - FY23-24"
    doc1 = (await db.execute(select(Document).where(Document.id == doc1_id))).scalar_one()
    bucket1 = (await db.execute(select(Bucket).where(Bucket.id == doc1.bucket_id))).scalar_one()
    assert bucket1.name == "Audit - FY23-24"

    # Verify bucket 2 is "Audit - FY24-25"
    doc2 = (await db.execute(select(Document).where(Document.id == doc2_id))).scalar_one()
    bucket2 = (await db.execute(select(Bucket).where(Bucket.id == doc2.bucket_id))).scalar_one()
    assert bucket2.name == "Audit - FY24-25"

    assert bucket1.id != bucket2.id


@pytest.mark.asyncio
async def test_external_docvault_document_attachment_and_auditor_download(client: AsyncClient, db: AsyncSession):
    """Verify external DocVault documents attached by company can be downloaded by auditors holding requirements permission."""
    await create_test_company(client, email="ext_doc@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='ext_doc@co.com', password='pass1234')}"}
    
    # Auditor with requirements: True, documents: False (testing that requirements permission alone grants access to attached external docs)
    await create_test_auditor(client, email="aud_ext@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='aud_ext@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers)
    inv = await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "aud_ext@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)
    
    aud_id = next(a["auditor_id"] for a in inv.json()["auditors"] if a["email"] == "aud_ext@aud.com")
    await client.patch(
        f"/api/v1/auditease/engagements/{eng_id}/auditors/{aud_id}",
        json={"area_permissions": {"trial_balance": True, "entries": True, "requirements": True, "queries": True, "documents": False}},
        headers=co_headers,
    )

    # 1. Company uploads external document in DocVault (outside audit bucket)
    dv_resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "External Balance Sheet 2024"},
        files={"file": ("annual_balance_sheet.pdf", b"EXTERNAL_SECRET_BALANCE_SHEET_BYTES", "application/pdf")},
        headers=co_headers,
    )
    assert dv_resp.status_code == 201
    ext_doc_id = dv_resp.json()["id"]

    # 2. Auditor creates requirement
    req_resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Please provide annual balance sheet"},
        headers=aud_headers,
    )
    req_id = req_resp.json()["id"]

    # 3. Company attaches the external document to this requirement
    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Attached the annual balance sheet from DocVault", "document_ids": [ext_doc_id]},
        headers=co_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["submission_count"] == 1
    assert resp.json()["document_count"] == 1

    # 4. Auditor downloads the external document via auditor document download endpoint
    dl_resp = await client.get(f"/api/v1/auditor/documents/{ext_doc_id}/download", headers=aud_headers)
    assert dl_resp.status_code == 200, dl_resp.text
    assert dl_resp.content == b"EXTERNAL_SECRET_BALANCE_SHEET_BYTES"

    # 5. Auditor metadata endpoint also succeeds
    meta_resp = await client.get(f"/api/v1/auditor/documents/{ext_doc_id}", headers=aud_headers)
    assert meta_resp.status_code == 200
    assert meta_resp.json()["title"] == "External Balance Sheet 2024"

    # 6. Unassigned auditor cannot download
    await create_test_auditor(client, email="unassigned_aud@aud.com", password="pass1234")
    unassigned_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='unassigned_aud@aud.com', password='pass1234')}"}
    bad_dl = await client.get(f"/api/v1/auditor/documents/{ext_doc_id}/download", headers=unassigned_headers)
    assert bad_dl.status_code == 404


@pytest.mark.asyncio
async def test_multiple_submissions_and_query_file_uploads_stored_in_engagement_bucket(
    client: AsyncClient, db: AsyncSession
):
    """Verify company can upload multiple direct files across multiple rounds and queries,
    and all attachments are stored in the dedicated engagement DocVault bucket and downloadable by the auditor."""
    await create_test_company(client, email="multi_subs@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='multi_subs@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="aud_ms@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='aud_ms@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers, label="FY2024")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "aud_ms@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    # 1. Auditor opens a requirement
    req_resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Please provide bank statements and payroll records"},
        headers=aud_headers,
    )
    req_id = req_resp.json()["id"]

    # 2. Company Round 1: Uploads 2 direct files
    resp1 = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Round 1 bank statements"},
        files=[
            ("files", ("bank_jan.pdf", b"BANK_JANUARY_DATA_BYTES", "application/pdf")),
            ("files", ("bank_feb.pdf", b"BANK_FEBRUARY_DATA_BYTES", "application/pdf")),
        ],
        headers=co_headers,
    )
    assert resp1.status_code == 200
    sub1_data = resp1.json()["submissions"][0]
    assert len(sub1_data["documents"]) == 2
    doc_jan_id = sub1_data["documents"][0]["document_id"]
    doc_feb_id = sub1_data["documents"][1]["document_id"]

    # 3. Company Round 2: Uploads another direct file
    resp2 = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Round 2 payroll summary"},
        files=[("files", ("payroll.xlsx", b"PAYROLL_SPREADSHEET_BYTES", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
        headers=co_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["submission_count"] == 2
    # Submissions are reverse ordered: submissions[0] is Round 2, submissions[1] is Round 1
    sub2_data = resp2.json()["submissions"][0]
    assert sub2_data["round_number"] == 2
    doc_payroll_id = sub2_data["documents"][0]["document_id"]

    # 4. Verify all documents are stored under bucket "Audit - FY2024" in DocVault
    for d_id in [doc_jan_id, doc_feb_id, doc_payroll_id]:
        doc_obj = (await db.execute(select(Document).where(Document.id == uuid.UUID(d_id)))).scalar_one()
        bucket_obj = (await db.execute(select(Bucket).where(Bucket.id == doc_obj.bucket_id))).scalar_one()
        assert bucket_obj.name == "Audit - FY2024"
        assert bucket_obj.visibility == BucketVisibility.everyone

    # 5. Auditor downloads all 3 documents directly
    dl_jan = await client.get(f"/api/v1/auditor/documents/{doc_jan_id}/download", headers=aud_headers)
    assert dl_jan.status_code == 200
    assert dl_jan.content == b"BANK_JANUARY_DATA_BYTES"

    dl_feb = await client.get(f"/api/v1/auditor/documents/{doc_feb_id}/download", headers=aud_headers)
    assert dl_feb.status_code == 200
    assert dl_feb.content == b"BANK_FEBRUARY_DATA_BYTES"

    dl_payroll = await client.get(f"/api/v1/auditor/documents/{doc_payroll_id}/download", headers=aud_headers)
    assert dl_payroll.status_code == 200
    assert dl_payroll.content == b"PAYROLL_SPREADSHEET_BYTES"

    # 6. Auditor opens a query
    q_resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/queries",
        data={"initial_message": "Need invoice sample #102"},
        headers=aud_headers,
    )
    q_id = q_resp.json()["id"]

    # 7. Company replies to query with direct file upload
    reply_resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/queries/{q_id}/messages",
        data={"text": "Here is invoice #102 attached"},
        files={"file": ("invoice_102.pdf", b"INVOICE_102_CONTENT_BYTES", "application/pdf")},
        headers=co_headers,
    )
    assert reply_resp.status_code == 200
    query_doc_id = reply_resp.json()["attached_document_id"]
    assert query_doc_id is not None

    # Verify query attachment is stored in "Audit - FY2024" bucket
    q_doc_obj = (await db.execute(select(Document).where(Document.id == uuid.UUID(query_doc_id)))).scalar_one()
    q_bucket_obj = (await db.execute(select(Bucket).where(Bucket.id == q_doc_obj.bucket_id))).scalar_one()
    assert q_bucket_obj.name == "Audit - FY2024"

    # Auditor downloads the query attachment
    dl_q = await client.get(f"/api/v1/auditor/documents/{query_doc_id}/download", headers=aud_headers)
    assert dl_q.status_code == 200
    assert dl_q.content == b"INVOICE_102_CONTENT_BYTES"


@pytest.mark.asyncio
async def test_auditor_cannot_access_unsubmitted_company_documents(client: AsyncClient, db: AsyncSession):
    """Verify that an auditor cannot download or read metadata for company documents that were not submitted in any requirement or query."""
    await create_test_company(client, email="unsub_co@co.com", password="pass1234")
    co_headers = {"Authorization": f"Bearer {await get_company_token(client, email='unsub_co@co.com', password='pass1234')}"}
    await create_test_auditor(client, email="unsub_aud@aud.com", password="pass1234")
    aud_headers = {"Authorization": f"Bearer {await get_auditor_token(client, email='unsub_aud@aud.com', password='pass1234')}"}

    eng_id = await _make_engagement(client, co_headers, label="FY2025")
    await client.post(f"/api/v1/auditease/engagements/{eng_id}/auditors/invite", json={"email": "unsub_aud@aud.com"}, headers=co_headers)
    await client.post(f"/api/v1/auditor/engagements/{eng_id}/accept", headers=aud_headers)

    # 1. Company uploads a private document in DocVault (e.g. board minutes, trade secrets)
    dv_resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Private Board Minutes 2025"},
        files={"file": ("board_minutes.pdf", b"TOP_SECRET_BOARD_MINUTES_BYTES", "application/pdf")},
        headers=co_headers,
    )
    assert dv_resp.status_code == 201
    private_doc_id = dv_resp.json()["id"]

    # 2. Company also uploads a document that WILL be submitted
    sub_resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Submitted Tax Return"},
        files={"file": ("tax_return.pdf", b"PUBLIC_TAX_RETURN_BYTES", "application/pdf")},
        headers=co_headers,
    )
    assert sub_resp.status_code == 201
    submitted_doc_id = sub_resp.json()["id"]

    # 3. Auditor creates a requirement
    req_resp = await client.post(
        f"/api/v1/auditor/engagements/{eng_id}/requirement-requests",
        json={"description": "Please upload tax return"},
        headers=aud_headers,
    )
    req_id = req_resp.json()["id"]

    # 4. Company submits ONLY the tax return document
    resp = await client.post(
        f"/api/v1/auditease/engagements/{eng_id}/requirement-requests/{req_id}/respond",
        data={"text_answer": "Tax return attached", "document_ids": [submitted_doc_id]},
        headers=co_headers,
    )
    assert resp.status_code == 200

    # 5. Auditor can download the submitted tax return
    tax_dl = await client.get(f"/api/v1/auditor/documents/{submitted_doc_id}/download", headers=aud_headers)
    assert tax_dl.status_code == 200
    assert tax_dl.content == b"PUBLIC_TAX_RETURN_BYTES"

    # 6. Auditor CANNOT download the unsubmitted board minutes (assert 404)
    bad_dl = await client.get(f"/api/v1/auditor/documents/{private_doc_id}/download", headers=aud_headers)
    assert bad_dl.status_code == 404

    # 7. Auditor CANNOT fetch metadata for the unsubmitted board minutes (assert 404)
    bad_meta = await client.get(f"/api/v1/auditor/documents/{private_doc_id}", headers=aud_headers)
    assert bad_meta.status_code == 404


@pytest.mark.asyncio
async def test_employee_user_picker_bucket_scoping(client: AsyncClient, db: AsyncSession):
    """Verify that non-admin company users (e.g. employee role) only see buckets and documents they have access to in DocVault."""
    await create_test_company(client, email="scope_admin@co.com", password="pass1234")
    admin_headers = {"Authorization": f"Bearer {await get_company_token(client, email='scope_admin@co.com', password='pass1234')}"}

    # Create employee user
    u_resp = await client.post(
        "/api/v1/users",
        json={
            "email": "scope_emp@co.com",
            "password": "pass1234password",
            "full_name": "Scope Employee",
            "role": "employee",
            "accessible_modules": ["auditease", "docvault"],
        },
        headers=admin_headers,
    )
    assert u_resp.status_code == 201, u_resp.text
    emp_headers = {"Authorization": f"Bearer {await get_company_token(client, email='scope_emp@co.com', password='pass1234password')}"}

    # Admin creates a public bucket (visibility=everyone)
    b_pub_resp = await client.post("/api/v1/docvault/buckets", json={"name": "Public General Bucket"}, headers=admin_headers)
    assert b_pub_resp.status_code == 201
    pub_bucket_id = b_pub_resp.json()["id"]

    # Admin creates a restricted bucket (visibility=restricted, not granted to employee)
    b_rest_resp = await client.post("/api/v1/docvault/buckets", json={"name": "Executive Restricted Bucket"}, headers=admin_headers)
    assert b_rest_resp.status_code == 201
    rest_bucket_id = b_rest_resp.json()["id"]
    patch_access = await client.patch(
        f"/api/v1/docvault/buckets/{rest_bucket_id}/access",
        json={"visibility": "restricted", "user_ids": []},
        headers=admin_headers,
    )
    assert patch_access.status_code == 200

    # Admin uploads doc to public bucket and doc to restricted bucket
    await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Public SOP Document", "bucket_id": pub_bucket_id},
        files={"file": ("sop.pdf", b"SOP_BYTES", "application/pdf")},
        headers=admin_headers,
    )
    await client.post(
        "/api/v1/docvault/documents",
        data={"title": "Executive Payroll Summary", "bucket_id": rest_bucket_id},
        files={"file": ("payroll.pdf", b"PAYROLL_SECRET_BYTES", "application/pdf")},
        headers=admin_headers,
    )

    # Employee lists buckets: should only see the public bucket
    emp_buckets_resp = await client.get("/api/v1/docvault/buckets", headers=emp_headers)
    assert emp_buckets_resp.status_code == 200
    emp_bucket_ids = [b["id"] for b in emp_buckets_resp.json()]
    assert pub_bucket_id in emp_bucket_ids
    assert rest_bucket_id not in emp_bucket_ids

    # Employee lists documents: should only see documents from accessible buckets
    emp_docs_resp = await client.get("/api/v1/docvault/documents", headers=emp_headers)
    assert emp_docs_resp.status_code == 200
    emp_doc_titles = [d["title"] for d in emp_docs_resp.json()]
    assert "Public SOP Document" in emp_doc_titles
    assert "Executive Payroll Summary" not in emp_doc_titles


