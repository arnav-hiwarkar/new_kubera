import pytest
from httpx import AsyncClient

from tests.conftest import create_test_company, get_company_token
from app.models.compliance import ComplianceDomain


async def _create_employee(client: AsyncClient, admin_headers: dict, email: str, modules: list[str]):
    response = await client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": "pass1234",
            "full_name": email.split("@")[0],
            "role": "employee",
            "accessible_modules": modules,
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    token = await get_company_token(client, email=email, password="pass1234")
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_secretarial_flow(client: AsyncClient):
    await create_test_company(client, email="sec@a.com", password="pass1234")
    token = await get_company_token(client, email="sec@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {token}"}

    # Create document type
    dt_data = {
        "name": "Minutes of Meeting",
        "metadata_schema": {"type": "object", "properties": {"date": {"type": "string"}}}
    }
    resp = await client.post("/api/v1/secretarial/document-types", json=dt_data, headers=headers)
    assert resp.status_code == 201
    dt_id = resp.json()["id"]
    
    # List document types
    resp = await client.get("/api/v1/secretarial/document-types", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    
    # Create meeting record
    mr_data = {
        "doc_type_id": dt_id,
        "structured_metadata": {"date": "2023-10-01"}
    }
    resp = await client.post("/api/v1/secretarial/meeting-records", json=mr_data, headers=headers)
    assert resp.status_code == 201
    mr_id = resp.json()["id"]
    
    # List meeting records
    resp = await client.get("/api/v1/secretarial/meeting-records", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_roc_flow(client: AsyncClient):
    await create_test_company(client, email="roc@a.com", password="pass1234")
    token = await get_company_token(client, email="roc@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {token}"}

    # Create document type
    dt_data = {
        "name": "AOC-4",
        "due_date_rule": "30 days from AGM"
    }
    resp = await client.post("/api/v1/roc/document-types", json=dt_data, headers=headers)
    assert resp.status_code == 201
    dt_id = resp.json()["id"]
    
    # Create meeting record (roc filing)
    mr_data = {
        "doc_type_id": dt_id
    }
    resp = await client.post("/api/v1/roc/meeting-records", json=mr_data, headers=headers)
    assert resp.status_code == 201
    
    # List
    resp = await client.get("/api/v1/roc/meeting-records", headers=headers)
    assert len(resp.json()) == 1
    
    # Secretarial should not see ROC records
    resp = await client.get("/api/v1/secretarial/meeting-records", headers=headers)
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_cross_tenant_compliance(client: AsyncClient):
    await create_test_company(client, email="c1@a.com", password="pass1234")
    token1 = await get_company_token(client, email="c1@a.com", password="pass1234")
    h1 = {"Authorization": f"Bearer {token1}"}
    
    await create_test_company(client, email="c2@a.com", password="pass1234")
    token2 = await get_company_token(client, email="c2@a.com", password="pass1234")
    h2 = {"Authorization": f"Bearer {token2}"}

    # C1 creates dt
    resp = await client.post("/api/v1/secretarial/document-types", json={"name": "C1 Doc"}, headers=h1)
    dt_id = resp.json()["id"]
    
    # C2 cannot see C1 dt
    resp = await client.get("/api/v1/secretarial/document-types", headers=h2)
    assert not any(d["name"] == "C1 Doc" for d in resp.json())
    
    # C2 cannot update C1 dt
    resp = await client.put(f"/api/v1/secretarial/document-types/{dt_id}", json={"name": "Hacked"}, headers=h2)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_record_date_roundtrip(client: AsyncClient):
    await create_test_company(client, email="rd@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='rd@a.com', password='pass1234')}"}

    dt_id = (await client.post("/api/v1/roc/document-types", json={"name": "Monthly Return"}, headers=headers)).json()["id"]
    resp = await client.post(
        "/api/v1/roc/meeting-records",
        json={"doc_type_id": dt_id, "record_date": "2026-07-05", "structured_metadata": {"ref": "R-1"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["record_date"] == "2026-07-05"

    rows = (await client.get("/api/v1/roc/meeting-records", headers=headers)).json()
    assert rows[0]["record_date"] == "2026-07-05"


@pytest.mark.asyncio
async def test_delete_type_guarded_by_records(client: AsyncClient):
    await create_test_company(client, email="del@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='del@a.com', password='pass1234')}"}

    # Type with a record cannot be deleted
    used = (await client.post("/api/v1/secretarial/document-types", json={"name": "Used"}, headers=headers)).json()["id"]
    await client.post("/api/v1/secretarial/meeting-records", json={"doc_type_id": used}, headers=headers)
    resp = await client.delete(f"/api/v1/secretarial/document-types/{used}", headers=headers)
    assert resp.status_code == 409

    # An empty type deletes fine
    empty = (await client.post("/api/v1/secretarial/document-types", json={"name": "Empty"}, headers=headers)).json()["id"]
    resp = await client.delete(f"/api/v1/secretarial/document-types/{empty}", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_record_rejects_wrong_domain_type(client: AsyncClient):
    await create_test_company(client, email="dom@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='dom@a.com', password='pass1234')}"}
    roc_dt = (await client.post("/api/v1/roc/document-types", json={"name": "ROC only"}, headers=headers)).json()["id"]
    # Using a ROC type under the secretarial domain must be rejected.
    resp = await client.post("/api/v1/secretarial/meeting-records", json={"doc_type_id": roc_dt}, headers=headers)
    assert resp.status_code == 400


async def _upload_to_domain_bucket(
    client: AsyncClient, headers: dict, domain: str, title: str, body: bytes = b"contents"
) -> str:
    """Put a file straight into the domain's docVault bucket, as a user would."""
    bucket = (await client.get(f"/api/v1/{domain}/bucket", headers=headers)).json()
    resp = await client.post(
        "/api/v1/docvault/documents",
        data={"title": title, "bucket_id": bucket["id"]},
        files={"file": (f"{title}.pdf", body, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_record_can_be_created_untyped_and_classified_later(client: AsyncClient):
    await create_test_company(client, email="untyped@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='untyped@a.com', password='pass1234')}"}

    # A record may be staged with nothing but a title.
    resp = await client.post(
        "/api/v1/secretarial/meeting-records",
        json={"title": "Awaiting classification"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["doc_type_id"] is None
    assert created["document_id"] is None
    assert created["domain"] == ComplianceDomain.secretarial.value

    # It is listed by its own domain and not the other one.
    assert len((await client.get("/api/v1/secretarial/meeting-records", headers=headers)).json()) == 1
    assert len((await client.get("/api/v1/roc/meeting-records", headers=headers)).json()) == 0

    # Classifying it later fills in the details.
    dt_id = (await client.post("/api/v1/secretarial/document-types", json={"name": "Board Minutes"}, headers=headers)).json()["id"]
    resp = await client.patch(
        f"/api/v1/secretarial/meeting-records/{created['id']}",
        json={"doc_type_id": dt_id, "record_date": "2026-05-01", "structured_metadata": {"ref": "BM-1"}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    patched = resp.json()
    assert patched["doc_type_id"] == dt_id
    assert patched["record_date"] == "2026-05-01"
    assert patched["structured_metadata"] == {"ref": "BM-1"}
    # An omitted field is left alone rather than cleared.
    assert patched["title"] == "Awaiting classification"


@pytest.mark.asyncio
async def test_docvault_sync_imports_bucket_documents_once(client: AsyncClient):
    await create_test_company(client, email="sync@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='sync@a.com', password='pass1234')}"}

    # Nothing in the bucket yet.
    assert (await client.get("/api/v1/roc/meeting-records/unsynced", headers=headers)).json() == []

    doc_id = await _upload_to_domain_bucket(client, headers, "roc", "AOC-4 filing")

    unsynced = (await client.get("/api/v1/roc/meeting-records/unsynced", headers=headers)).json()
    assert [d["id"] for d in unsynced] == [doc_id]
    assert unsynced[0]["title"] == "AOC-4 filing"
    assert unsynced[0]["original_filename"] == "AOC-4 filing.pdf"

    resp = await client.post("/api/v1/roc/meeting-records/sync", headers=headers)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["imported"] == 1
    assert result["records"][0]["document_id"] == doc_id
    assert result["records"][0]["doc_type_id"] is None
    assert result["records"][0]["title"] == "AOC-4 filing"

    # Now synced: the button's count drops to zero and a second sync is a no-op.
    assert (await client.get("/api/v1/roc/meeting-records/unsynced", headers=headers)).json() == []
    assert (await client.post("/api/v1/roc/meeting-records/sync", headers=headers)).json()["imported"] == 0
    assert len((await client.get("/api/v1/roc/meeting-records", headers=headers)).json()) == 1


@pytest.mark.asyncio
async def test_sync_is_isolated_per_domain(client: AsyncClient):
    await create_test_company(client, email="syncdom@a.com", password="pass1234")
    headers = {"Authorization": f"Bearer {await get_company_token(client, email='syncdom@a.com', password='pass1234')}"}

    await _upload_to_domain_bucket(client, headers, "roc", "ROC only doc")

    # A ROC bucket document is invisible to SecretarialEase.
    assert (await client.get("/api/v1/secretarial/meeting-records/unsynced", headers=headers)).json() == []
    assert (await client.post("/api/v1/secretarial/meeting-records/sync", headers=headers)).json()["imported"] == 0

    record_id = (await client.post("/api/v1/roc/meeting-records/sync", headers=headers)).json()["records"][0]["id"]

    # And a ROC record cannot be edited through the secretarial prefix.
    resp = await client.patch(
        f"/api/v1/secretarial/meeting-records/{record_id}", json={"title": "Hijacked"}, headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_rejects_foreign_and_wrong_domain_types(client: AsyncClient):
    await create_test_company(client, email="patch1@a.com", password="pass1234")
    h1 = {"Authorization": f"Bearer {await get_company_token(client, email='patch1@a.com', password='pass1234')}"}
    await create_test_company(client, email="patch2@a.com", password="pass1234")
    h2 = {"Authorization": f"Bearer {await get_company_token(client, email='patch2@a.com', password='pass1234')}"}

    record_id = (await client.post("/api/v1/secretarial/meeting-records", json={"title": "Mine"}, headers=h1)).json()["id"]

    # A type from the other domain is rejected.
    roc_dt = (await client.post("/api/v1/roc/document-types", json={"name": "ROC only"}, headers=h1)).json()["id"]
    resp = await client.patch(f"/api/v1/secretarial/meeting-records/{record_id}", json={"doc_type_id": roc_dt}, headers=h1)
    assert resp.status_code == 400

    # A type owned by another company is rejected.
    foreign_dt = (await client.post("/api/v1/secretarial/document-types", json={"name": "Theirs"}, headers=h2)).json()["id"]
    resp = await client.patch(f"/api/v1/secretarial/meeting-records/{record_id}", json={"doc_type_id": foreign_dt}, headers=h1)
    assert resp.status_code == 400

    # And another company cannot touch the record at all.
    resp = await client.patch(f"/api/v1/secretarial/meeting-records/{record_id}", json={"title": "Hacked"}, headers=h2)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_compliance_module_access_is_independent_and_server_enforced(client: AsyncClient):
    await create_test_company(client, email="permissions-admin@a.com", password="pass1234")
    admin_headers = {
        "Authorization": (
            "Bearer "
            + await get_company_token(
                client, email="permissions-admin@a.com", password="pass1234"
            )
        )
    }

    roc_only = await _create_employee(client, admin_headers, "roc-only@a.com", ["roc"])
    secretarial_only = await _create_employee(
        client, admin_headers, "secretarial-only@a.com", ["secretarial"]
    )
    neither = await _create_employee(client, admin_headers, "neither@a.com", [])
    both = await _create_employee(
        client, admin_headers, "both@a.com", ["roc", "secretarial"]
    )

    # Admins bypass stored module grants and can use both domains.
    assert (
        await client.get("/api/v1/roc/document-types", headers=admin_headers)
    ).status_code == 200
    assert (
        await client.get("/api/v1/secretarial/document-types", headers=admin_headers)
    ).status_code == 200

    assert (await client.get("/api/v1/roc/document-types", headers=roc_only)).status_code == 200
    assert (
        await client.get("/api/v1/secretarial/document-types", headers=roc_only)
    ).status_code == 403

    assert (
        await client.get("/api/v1/secretarial/document-types", headers=secretarial_only)
    ).status_code == 200
    assert (
        await client.get("/api/v1/roc/document-types", headers=secretarial_only)
    ).status_code == 403

    for path in ("roc", "secretarial"):
        assert (
            await client.get(f"/api/v1/{path}/document-types", headers=neither)
        ).status_code == 403
        assert (
            await client.get(f"/api/v1/{path}/document-types", headers=both)
        ).status_code == 200

    forbidden = await client.post(
        "/api/v1/secretarial/document-types",
        json={"name": "Must not be created"},
        headers=roc_only,
    )
    assert forbidden.status_code == 403
    rows = (
        await client.get("/api/v1/secretarial/document-types", headers=admin_headers)
    ).json()
    assert not any(row["name"] == "Must not be created" for row in rows)

    assert (
        await client.post(
            "/api/v1/roc/document-types",
            json={"name": "ROC permitted"},
            headers=roc_only,
        )
    ).status_code == 201
    assert (
        await client.post(
            "/api/v1/secretarial/document-types",
            json={"name": "Secretarial permitted"},
            headers=secretarial_only,
        )
    ).status_code == 201
