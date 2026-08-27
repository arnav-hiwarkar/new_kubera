import uuid
from httpx import AsyncClient
import pytest
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditease import RequirementResponse, RequirementResponseDocument
from app.models.docvault import Document, DocumentAccessOverride, Bucket
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
    assert rounds == [1, 2, 3]


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
    assert bucket.name == "Audit Attachments"


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
